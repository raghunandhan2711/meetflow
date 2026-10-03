"""HTTP endpoints for meeting capture, search, analysis, and Jira delivery."""
from pathlib import Path
from uuid import uuid4
from fastapi import APIRouter, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import Response
from sqlalchemy import select, update, or_
from .config import ROOT, settings
from .database import Session, Meeting, Task
from .schemas import TranscriptInput, TaskUpdate
from .sample import sample_meeting
from .pipeline import process_meeting, ACTIVE
from .serialization import task_dict, meeting_dict
from . import services, security

router = APIRouter()
MAX_UPLOAD = 24 * 1024 * 1024


@router.get('/api/health')
def health():
    with Session() as db:
        db.execute(select(1))
    return {'status': 'ok'}


@router.get('/api/settings')
def configuration():
    return {'groq': bool(settings.groq_api_key), 'model': settings.groq_model, 'transcription': settings.transcription_provider, 'diarization': settings.diarization_enabled, 'huggingface': bool(settings.hf_token), 'jira': settings.jira_ready, 'jira_project': settings.jira_project_key, 'database': 'PostgreSQL' if settings.database_url.startswith('postgresql') else 'SQLite (local)', 'max_upload_mb': 24}


@router.get('/api/meetings')
def meetings(q: str = ''):
    with Session() as db:
        stmt = select(Meeting).order_by(Meeting.created_at.desc())
        if q:
            needle = '%' + q[:200].replace('%', '\\%').replace('_', '\\_') + '%'
            stmt = stmt.where(or_(Meeting.title.ilike(needle, escape='\\'), Meeting.transcript.ilike(needle, escape='\\'), Meeting.summary.ilike(needle, escape='\\')))
        return [meeting_dict(m, False) for m in db.scalars(stmt).all()]


@router.get('/api/meetings/{meeting_id}')
def meeting(meeting_id: str):
    with Session() as db:
        m = db.get(Meeting, meeting_id)
        if not m:
            raise HTTPException(404, 'Meeting not found.')
        return meeting_dict(m)


@router.post('/api/sample', status_code=201)
def create_sample():
    with Session() as db:
        m = db.scalar(select(Meeting).where(Meeting.source == 'sample'))
        if not m:
            m = sample_meeting()
            db.add(m)
            db.commit()
        return meeting_dict(m)


@router.post('/api/meetings', status_code=202)
def create_meeting(body: TranscriptInput, background: BackgroundTasks):
    if not body.title.strip() or len(body.transcript.strip()) < 30:
        raise HTTPException(422, 'Enter a title and at least 30 characters of transcript.')
    with Session() as db:
        m = Meeting(title=security.redact(body.title.strip()), transcript=security.redact(body.transcript.strip()))
        db.add(m)
        db.commit()
        background.add_task(process_meeting, m.id)
        return meeting_dict(m)


@router.post('/api/upload', status_code=202)
async def upload(background: BackgroundTasks, title: str = Form(...), audio: UploadFile = File(...)):
    title = title.strip()
    if not title or len(title) > 180:
        raise HTTPException(422, 'A title between 1 and 180 characters is required.')
    suffix = Path(audio.filename or '').suffix.lower()
    if suffix not in {'.mp3', '.mp4', '.m4a', '.wav', '.webm', '.ogg', '.flac'}:
        raise HTTPException(415, 'Choose an MP3, MP4, M4A, WAV, WebM, OGG, or FLAC recording.')
    path = ROOT / 'data' / 'uploads' / f'{uuid4()}{suffix}'
    size = 0
    try:
        with path.open('wb') as out:
            while chunk := await audio.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD:
                    raise HTTPException(413, 'Recording exceeds the 24 MB upload limit.')
                out.write(chunk)
        if size == 0:
            raise HTTPException(422, 'The recording is empty.')
        with Session() as db:
            m = Meeting(title=security.redact(title), source='audio', audio_file=path.name, original_filename=security.redact((audio.filename or 'Recording')[:250]))
            db.add(m)
            db.commit()
            background.add_task(process_meeting, m.id, str(path))
            return meeting_dict(m)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    finally:
        await audio.close()


@router.post('/api/meetings/{meeting_id}/retry', status_code=202)
def retry(meeting_id: str, background: BackgroundTasks):
    with Session() as db:
        m = db.get(Meeting, meeting_id)
        if not m:
            raise HTTPException(404, 'Meeting not found.')
        if m.status not in ('failed', 'transcribed') or not (m.transcript or m.audio_file):
            raise HTTPException(409, 'This meeting cannot be processed again in its current state.')
        if m.transcript and not settings.groq_api_key:
            raise HTTPException(409, 'AI analysis is waiting for the Groq API credential. Your transcript is saved.')
        result = db.execute(update(Meeting).where(Meeting.id == meeting_id, Meeting.status.in_(['failed', 'transcribed'])).values(status='queued', error=''))
        if result.rowcount != 1:
            raise HTTPException(409, 'This meeting is already processing.')
        db.commit()
        background.add_task(process_meeting, meeting_id, str(ROOT / 'data' / 'uploads' / m.audio_file) if not m.transcript and m.audio_file else None)
        return {'status': 'queued'}


@router.patch('/api/tasks/{task_id}')
def edit_task(task_id: str, body: TaskUpdate):
    with Session() as db:
        t = db.get(Task, task_id)
        if not t:
            raise HTTPException(404, 'Task not found.')
        changes = body.model_dump(exclude_unset=True, exclude_none=True)
        if 'title' in changes:
            changes['title'] = changes['title'].strip()
            if not changes['title']:
                raise HTTPException(422, 'Enter a task title.')
        if t.jira_status != 'not_sent' and any(k != 'status' for k in changes):
            raise HTTPException(409, 'Edit this task in Jira after it has been sent.')
        for key, value in changes.items():
            setattr(t, key, security.redact(value))
        db.commit()
        return task_dict(t)


@router.post('/api/tasks/{task_id}/jira')
def send_to_jira(task_id: str):
    with Session() as db:
        t = db.get(Task, task_id)
        if not t:
            raise HTTPException(404, 'Task not found.')
        if t.jira_key:
            return task_dict(t)
        if not settings.jira_ready:
            raise HTTPException(409, 'Jira credentials have not been configured yet. This task is saved and can be sent after Jira is connected.')
        claimed = db.execute(update(Task).where(Task.id == task_id, Task.jira_status == 'not_sent').values(jira_status='sending'))
        if claimed.rowcount != 1:
            raise HTTPException(409, 'This task is already sending or needs verification in Jira. Automatic retries are disabled to prevent duplicate tickets.')
        db.commit()
        try:
            t.jira_key = services.create_jira(t, db.get(Meeting, t.meeting_id))
            t.jira_status = 'sent'
            db.commit()
        except Exception as exc:
            t.jira_status = 'not_sent' if isinstance(exc, ValueError) else 'uncertain'
            db.commit()
            raise HTTPException(502, str(exc) if isinstance(exc, (ValueError, RuntimeError)) else 'Jira connection was interrupted. Check Jira for this task before retrying.') from exc
        return task_dict(t)


@router.get('/api/meetings/{meeting_id}/export')
def export(meeting_id: str):
    m = meeting(meeting_id)
    text = f"# {m['title']}\n\n{m['summary']}\n\n## Decisions\n" + '\n'.join('- ' + d for d in m['decisions'])
    text += '\n\n## Action items\n' + '\n'.join(f"- [{'x' if t['status'] == 'done' else ' '}] {t['title']} — {t['owner']} | {t['due_date'] or 'No due date'} | {t['jira_key']}" for t in m['tasks'])
    text += '\n\n## Transcript\n\n' + m['transcript']
    return Response(text, media_type='text/markdown', headers={'Content-Disposition': 'attachment; filename="meeting-notes.md"'})

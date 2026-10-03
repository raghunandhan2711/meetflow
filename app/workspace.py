"""Meeting review, source playback, speaker correction, and task management."""
import csv
import html
import io
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel, Field
from .config import ROOT
from .database import Session, Meeting, Task
from .schemas import ActionItem
from .security import redact
from .pipeline import ACTIVE

router = APIRouter(prefix='/api')


class MeetingEdit(BaseModel):
    title: str = Field(min_length=1, max_length=180)


class SpeakerEdit(BaseModel):
    speaker: str = Field(min_length=1, max_length=120)
    name: str = Field(min_length=1, max_length=120)


def get_meeting(db, meeting_id):
    meeting = db.get(Meeting, meeting_id)
    if not meeting:
        raise HTTPException(404, 'Meeting not found.')
    return meeting


def require_idle(meeting):
    if meeting.status in ACTIVE:
        raise HTTPException(409, 'Wait for processing to finish before editing this meeting.')


@router.patch('/meetings/{meeting_id}')
def rename_meeting(meeting_id: str, body: MeetingEdit):
    if not body.title.strip():
        raise HTTPException(422, 'Enter a meeting title.')
    with Session() as db:
        meeting = get_meeting(db, meeting_id)
        meeting.title = redact(body.title.strip())
        db.commit()
    return {'status': 'saved'}


@router.get('/meetings/{meeting_id}/audio')
def play_audio(meeting_id: str):
    with Session() as db:
        meeting = get_meeting(db, meeting_id)
        filename = meeting.audio_file
        if not filename or Path(filename).name != filename:
            raise HTTPException(404, 'This meeting has no saved recording.')
        path = ROOT / 'data' / 'uploads' / filename
        if not path.is_file():
            raise HTTPException(404, 'The recording is unavailable.')
        return FileResponse(path)


@router.patch('/meetings/{meeting_id}/speakers')
def rename_speaker(meeting_id: str, body: SpeakerEdit):
    name = redact(body.name.strip())
    if not name or '\n' in name or ':' in name:
        raise HTTPException(422, 'Enter a name without a colon or line break.')
    with Session() as db:
        meeting = get_meeting(db, meeting_id)
        require_idle(meeting)
        if not any(s.get('speaker') == body.speaker for s in meeting.segments):
            raise HTTPException(404, 'Speaker not found in this transcript.')
        if name != body.speaker and any(s.get('speaker') == name for s in meeting.segments):
            raise HTTPException(409, 'That name is assigned to a different speaker.')
        meeting.segments = [{**s, 'speaker': name if s.get('speaker') == body.speaker else s.get('speaker', 'Unknown')} for s in meeting.segments]
        meeting.transcript = '\n'.join(f"{s['speaker']}: {s['text']}" for s in meeting.segments)
        for task in meeting.tasks:
            if task.owner == body.speaker and task.jira_status == 'not_sent':
                task.owner = name
        db.commit()
    return {'status': 'saved'}


@router.post('/meetings/{meeting_id}/tasks', status_code=201)
def add_task(meeting_id: str, body: ActionItem):
    with Session() as db:
        meeting = get_meeting(db, meeting_id)
        require_idle(meeting)
        if not body.title.strip():
            raise HTTPException(422, 'Enter a task title.')
        task = Task(meeting_id=meeting_id, origin='manual', position=max((t.position for t in meeting.tasks), default=-1)+1, **redact(body.model_dump()))
        db.add(task)
        db.commit()
        return {'id': task.id}


@router.delete('/tasks/{task_id}')
def delete_task(task_id: str):
    with Session() as db:
        task = db.get(Task, task_id)
        if not task:
            raise HTTPException(404, 'Task not found.')
        if task.jira_status != 'not_sent':
            raise HTTPException(409, 'Keep linked tasks for traceability. Manage the issue in Jira.')
        db.delete(task)
        db.commit()
    return {'status': 'deleted'}


@router.delete('/meetings/{meeting_id}')
def delete_meeting(meeting_id: str):
    with Session() as db:
        meeting = get_meeting(db, meeting_id)
        require_idle(meeting)
        if any(t.jira_status == 'sending' for t in meeting.tasks):
            raise HTTPException(409, 'Wait for Jira delivery to finish.')
        filename = meeting.audio_file
        db.delete(meeting)
        db.commit()
        if filename and Path(filename).name == filename:
            (ROOT / 'data' / 'uploads' / filename).unlink(missing_ok=True)
    return {'status': 'deleted'}


def csv_safe(value):
    value = redact(str(value or ''))
    return "'" + value if value.lstrip().startswith(('=', '+', '-', '@', '\t', '\r')) else value


@router.get('/meetings/{meeting_id}/tasks.csv')
def export_tasks(meeting_id: str):
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(['Task', 'Description', 'Owner', 'Due', 'Priority', 'Status', 'Jira', 'Source quote'])
    with Session() as db:
        meeting = get_meeting(db, meeting_id)
        for task in meeting.tasks:
            writer.writerow([csv_safe(getattr(task, key)) for key in ['title','description','owner','due_date','priority','status','jira_key','evidence']])
    return Response('\ufeff'+output.getvalue(), media_type='text/csv', headers={'Content-Disposition':'attachment; filename="action-items.csv"'})


@router.get('/meetings/{meeting_id}/report', response_class=HTMLResponse)
def report(meeting_id: str):
    e = lambda value: html.escape(redact(value))
    with Session() as db:
        m = get_meeting(db, meeting_id)
        tasks = ''.join(f'<tr><td>{e(t.title)}</td><td>{e(t.owner)}</td><td>{e(t.due_date or "Not specified")}</td><td>{e(t.status)}</td></tr>' for t in m.tasks)
        decisions = ''.join(f'<li>{e(d)}</li>' for d in m.decisions)
        return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{e(m.title)} — Meeting report</title><link rel="stylesheet" href="/static/report.css"></head><body><header>AI-POWERED MEETING ANALYSIS &amp; TASK AUTOMATION SYSTEM</header><main><p class="date">{m.created_at.strftime('%d %B %Y')} · {e(m.source)}</p><h1>{e(m.title)}</h1><p class="print-hint">Use your browser's Print command (Ctrl+P) to save this report as a PDF.</p><h2>Meeting summary</h2><p>{e(m.summary or "Analysis pending.")}</p><h2>Decisions</h2><ol>{decisions}</ol><h2>Action items</h2><table><thead><tr><th>Task</th><th>Owner</th><th>Due</th><th>Status</th></tr></thead><tbody>{tasks}</tbody></table><h2>Full transcript</h2><pre>{e(m.transcript)}</pre></main><footer>Meeting record · {e(m.id)}</footer></body></html>'''

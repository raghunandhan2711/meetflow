"""Meeting processing: recording -> transcript -> validated analysis -> saved tasks."""
import logging
from pathlib import Path
from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from .config import settings
from .database import Session, Meeting, Task, utcnow
from .records import ACTIVE
from . import services, security

log = logging.getLogger(__name__)


def process_meeting(meeting_id, audio_path=None):
    try:
        with Session() as db:
            claimed = db.execute(update(Meeting).where(Meeting.id == meeting_id, Meeting.status == 'queued').values(status='transcribing' if audio_path else 'analyzing'))
            if claimed.rowcount != 1:
                return
            db.commit()
        # Slow model/network work never holds a database connection or row lock.
        if audio_path:
            transcript, segments, duration = services.transcribe(Path(audio_path))
            with Session() as db:
                m = db.get(Meeting, meeting_id)
                m.transcript, m.segments, m.duration = transcript, segments, duration
                m.transcript_created_at = utcnow()
                db.commit()
        with Session() as db:
            m = db.get(Meeting, meeting_id)
            transcript = m.transcript
            if not settings.groq_api_key or len(transcript) > 80000:
                m.status = 'transcribed'
                m.error = ('Full transcript saved. AI analysis supports up to 80,000 characters; split it into shorter meetings.'
                           if len(transcript) > 80000 else 'Transcript saved. AI analysis is waiting for the Groq API credential.')
                db.commit()
                return
            m.status = 'analyzing'
            db.commit()
        result = services.analyze(transcript)
        with Session() as db:
            m = db.scalar(select(Meeting).where(Meeting.id == meeting_id).with_for_update())
            if not m or m.status != 'analyzing':
                return
            m.summary = result.summary
            m.topics = result.topics
            m.decisions = result.decisions
            m.analyzed_at = utcnow()
            m.analysis_model = settings.groq_model
            m.analysis_revision += 1
            protected = [t for t in m.tasks if t.origin == 'manual' or t.jira_status != 'not_sent' or t.status != 'open']
            titles = {t.title.casefold().strip() for t in protected}
            evidence = {t.evidence.casefold().strip() for t in protected if t.evidence}
            existing = {t.title.casefold().strip(): t for t in m.tasks if t not in protected}
            extracted = []
            for item in result.action_items:
                key = item.title.casefold().strip()
                if key in titles or (item.evidence and item.evidence.casefold().strip() in evidence):
                    continue
                task = existing.get(key) or Task()
                for name, value in item.model_dump().items():
                    setattr(task, name, value)
                extracted.append(task)
                titles.add(key)
            m.tasks = protected + extracted
            for position, task in enumerate(m.tasks):
                task.position = position
            m.status = 'ready'
            m.error = ''
            db.commit()
    except Exception as exc:
        log.warning('Meeting processing failed (%s)', type(exc).__name__)
        try:
            with Session() as db:
                m = db.get(Meeting, meeting_id)
                if m and m.status in ACTIVE:
                    m.status = 'failed'
                    m.error = security.redact(str(exc)) if isinstance(exc, ValueError) else 'Processing failed. Saved results are retained. Check the database, model installation or provider connection, then retry.'
                    db.commit()
        except SQLAlchemyError as error:
            log.error('Could not persist processing failure (%s); restart recovery will mark interrupted jobs.', type(error).__name__)

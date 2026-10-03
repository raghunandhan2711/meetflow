"""Meeting processing: recording -> transcript -> validated analysis -> saved tasks."""
import logging
from pathlib import Path
from .config import settings
from .database import Session, Meeting, Task
from . import services, security

log = logging.getLogger(__name__)
ACTIVE = ('queued', 'transcribing', 'analyzing')


def process_meeting(meeting_id, audio_path=None):
    try:
        with Session() as db:
            m = db.get(Meeting, meeting_id)
            if audio_path:
                m.status = 'transcribing'
                db.commit()
                m.transcript, m.segments, m.duration = services.transcribe(Path(audio_path))
                db.commit()
            if len(m.transcript) > 80000:
                raise ValueError('Transcript exceeds 80,000 characters. Split the recording into shorter meetings.')
            if not settings.groq_api_key:
                m.status = 'transcribed'
                m.error = 'Transcript saved. AI analysis is waiting for the Groq API credential.'
                db.commit()
                return
            m.status = 'analyzing'
            db.commit()
            result = services.analyze(m.transcript)
            m.summary = result.summary
            m.topics = result.topics
            m.decisions = result.decisions
            manual_tasks = [task for task in m.tasks if task.origin == 'manual']
            manual_titles = {task.title.casefold().strip() for task in manual_tasks}
            extracted_tasks = [Task(**task.model_dump()) for task in result.action_items if task.title.casefold().strip() not in manual_titles]
            m.tasks = manual_tasks + extracted_tasks
            for position, task in enumerate(m.tasks):
                task.position = position
            m.status = 'ready'
            m.error = ''
            db.commit()
    except Exception as exc:
        log.warning('Meeting processing failed (%s)', type(exc).__name__)
        with Session() as db:
            m = db.get(Meeting, meeting_id)
            if m:
                m.status = 'failed'
                m.error = security.redact(str(exc)) if isinstance(exc, ValueError) else 'Processing failed. Check model installation, network access, or provider configuration, then retry.'
                db.commit()

"""Public response shapes with centralized credential redaction."""
from .config import settings
from .database import Meeting, Task
from . import security


def task_dict(t):
    result = {c.name: getattr(t, c.name) for c in Task.__table__.columns}
    result['jira_url'] = f'{settings.jira_base_url.rstrip("/")}/browse/{t.jira_key}' if t.jira_key else ''
    return security.redact(result)


def meeting_dict(m, full=True):
    result = {c.name: getattr(m, c.name) for c in Meeting.__table__.columns if full or c.name != 'transcript'}
    result['has_audio'] = bool(m.audio_file)
    result.pop('audio_file', None)
    result['created_at'] = m.created_at.isoformat() + ('Z' if m.created_at.tzinfo is None else '')
    result['tasks'] = [task_dict(t) for t in m.tasks]
    result['speakers'] = sorted({s['speaker'] for s in m.segments if s.get('speaker') and s['speaker'] != 'Unknown'})
    if not full:
        result.pop('transcript', None)
        result.pop('segments')
    return security.redact(result)

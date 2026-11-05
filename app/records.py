"""Short row locks shared by write routes; no database session of its own."""
from fastapi import HTTPException
from sqlalchemy import select
from .database import Meeting, Task

ACTIVE = ('queued', 'transcribing', 'analyzing')


def locked_meeting(db, meeting_id, idle=True):
    meeting = db.scalar(select(Meeting).where(Meeting.id == meeting_id).with_for_update())
    if not meeting:
        raise HTTPException(404, 'Meeting not found.')
    if idle and meeting.status in ACTIVE:
        raise HTTPException(409, 'Wait for processing to finish before editing this meeting.')
    return meeting


def locked_task(db, task_id):
    meeting_id = db.scalar(select(Task.meeting_id).where(Task.id == task_id))
    if not meeting_id:
        raise HTTPException(404, 'Task not found.')
    # Always parent before child to keep lock order consistent with deletion.
    locked_meeting(db, meeting_id)
    task = db.scalar(select(Task).where(Task.id == task_id).with_for_update())
    if not task:
        raise HTTPException(404, 'Task not found.')
    return task

"""Database initialization and recovery after interrupted processing."""
from contextlib import asynccontextmanager
from sqlalchemy import inspect, text, update
from .database import Base, engine, Session, Meeting, Task
from . import security
from .pipeline import ACTIVE


@asynccontextmanager
async def lifespan(app):
    security.protect_logs()
    Base.metadata.create_all(engine)
    columns = {column['name'] for column in inspect(engine).get_columns('meetings')}
    with engine.begin() as connection:
        for name, length in [('audio_file', 100), ('original_filename', 250)]:
            if name not in columns:
                connection.execute(text(f"ALTER TABLE meetings ADD COLUMN {name} VARCHAR({length}) NOT NULL DEFAULT ''"))
        task_columns = {column['name'] for column in inspect(engine).get_columns('tasks')}
        if 'origin' not in task_columns:
            connection.execute(text("ALTER TABLE tasks ADD COLUMN origin VARCHAR(20) NOT NULL DEFAULT 'ai'"))
    with Session() as db:
        db.execute(update(Meeting).where(Meeting.status.in_(ACTIVE)).values(status='failed', error='Processing was interrupted by a server restart. Retry analysis or upload the audio again.'))
        db.execute(update(Task).where(Task.jira_status == 'sending').values(jira_status='uncertain'))
        db.commit()
    yield

"""Database initialization and recovery after interrupted processing."""
from contextlib import asynccontextmanager
import logging
from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError
from .database import engine, Session, Meeting, Task
from .migrations import migrate
from . import security
from .pipeline import ACTIVE


@asynccontextmanager
async def lifespan(app):
    security.protect_logs()
    try:
        migrate(engine)
        with Session() as db:
            db.execute(update(Meeting).where(Meeting.status.in_(ACTIVE)).values(status='failed', error='Processing was interrupted by a server restart. Retry using the retained transcript or recording.'))
            db.execute(update(Task).where(Task.jira_status == 'sending').values(jira_status='uncertain'))
            db.commit()
        yield
    except SQLAlchemyError as error:
        logging.getLogger(__name__).error('Database lifecycle failed (%s); credentials and SQL withheld.', type(error).__name__)
        raise RuntimeError('Database unavailable or migration failed. Check DATABASE_URL, start PostgreSQL, and run db:status.') from None
    finally:
        engine.dispose()

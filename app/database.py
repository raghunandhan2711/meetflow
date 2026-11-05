from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import create_engine, String, Text, JSON, ForeignKey, DateTime, event, CheckConstraint, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import make_url
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker
from .config import settings


class Base(DeclarativeBase):
    pass


def utcnow():
    return datetime.now(timezone.utc)


structured = JSON().with_variant(JSONB(), 'postgresql')


class Meeting(Base):
    __tablename__ = 'meetings'
    __table_args__ = (
        CheckConstraint("status IN ('queued','transcribing','analyzing','transcribed','ready','failed')", name='ck_meetings_status'),
        CheckConstraint("source IN ('transcript','audio','sample')", name='ck_meetings_source'),
        CheckConstraint('length(trim(title)) > 0', name='ck_meetings_title'),
        CheckConstraint('duration >= 0', name='ck_meetings_duration'),
        Index('ix_meetings_created_id', 'created_at', 'id'),
        Index('ix_meetings_status', 'status'),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    title: Mapped[str] = mapped_column(String(180))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    description: Mapped[str] = mapped_column(Text, default='')
    meeting_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    transcript_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    analyzed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    analysis_model: Mapped[str] = mapped_column(String(120), default='')
    analysis_revision: Mapped[int] = mapped_column(default=0)
    status: Mapped[str] = mapped_column(String(30), default='queued')
    source: Mapped[str] = mapped_column(String(30), default='transcript')
    transcript: Mapped[str] = mapped_column(Text, default='')
    segments: Mapped[list] = mapped_column(structured, default=list)
    summary: Mapped[str] = mapped_column(Text, default='')
    decisions: Mapped[list] = mapped_column(structured, default=list)
    topics: Mapped[list] = mapped_column(structured, default=list)
    error: Mapped[str] = mapped_column(Text, default='')
    duration: Mapped[float] = mapped_column(default=0.0)
    audio_file: Mapped[str] = mapped_column(String(100), default='')
    original_filename: Mapped[str] = mapped_column(String(250), default='')
    tasks: Mapped[list['Task']] = relationship(cascade='all, delete-orphan', order_by='Task.position')


class Task(Base):
    __tablename__ = 'tasks'
    __table_args__ = (
        CheckConstraint("status IN ('open','in_progress','done')", name='ck_tasks_status'),
        CheckConstraint("priority IN ('low','medium','high')", name='ck_tasks_priority'),
        CheckConstraint("origin IN ('ai','manual')", name='ck_tasks_origin'),
        CheckConstraint("jira_status IN ('not_sent','sending','sent','uncertain')", name='ck_tasks_jira_status'),
        CheckConstraint('length(trim(title)) > 0', name='ck_tasks_title'),
        Index('ix_tasks_meeting_status', 'meeting_id', 'status'),
    )
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    meeting_id: Mapped[str] = mapped_column(ForeignKey('meetings.id'), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    position: Mapped[int] = mapped_column(default=0)
    origin: Mapped[str] = mapped_column(String(20), default='ai')
    title: Mapped[str] = mapped_column(String(240))
    description: Mapped[str] = mapped_column(Text, default='')
    owner: Mapped[str] = mapped_column(String(120), default='Unassigned')
    due_date: Mapped[str] = mapped_column(String(50), default='')
    priority: Mapped[str] = mapped_column(String(20), default='medium')
    feature: Mapped[str] = mapped_column(String(120), default='')
    evidence: Mapped[str] = mapped_column(Text, default='')
    status: Mapped[str] = mapped_column(String(20), default='open')
    jira_key: Mapped[str] = mapped_column(String(50), default='')
    jira_status: Mapped[str] = mapped_column(String(20), default='not_sent')


def make_engine(url, **overrides):
    options = dict(pool_pre_ping=True, hide_parameters=True)
    if str(url).startswith('sqlite'):
        options['connect_args'] = {'check_same_thread': False, 'timeout': 10}
    else:
        # Preserve explicitly configured session options (e.g. isolated test schemas).
        session_options = make_url(url).query.get('options', '')
        options.update(pool_size=settings.db_pool_size, max_overflow=settings.db_max_overflow,
                       pool_timeout=settings.db_pool_timeout, pool_recycle=1800,
                       connect_args={'connect_timeout': settings.db_connect_timeout,
                                     'options': session_options + ' -c statement_timeout=30000 -c lock_timeout=10000'})
    options.update(overrides)
    result = create_engine(url, **options)
    if result.dialect.name == 'sqlite':
        @event.listens_for(result, 'connect')
        def enable_foreign_keys(connection, _):
            connection.execute('PRAGMA foreign_keys=ON')
    return result


engine = make_engine(settings.database_url)
Session = sessionmaker(engine, expire_on_commit=False)

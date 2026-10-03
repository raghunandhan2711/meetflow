from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import create_engine, String, Text, JSON, ForeignKey, DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker
from .config import settings


class Base(DeclarativeBase):
    pass


class Meeting(Base):
    __tablename__ = 'meetings'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    title: Mapped[str] = mapped_column(String(180))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    status: Mapped[str] = mapped_column(String(30), default='queued')
    source: Mapped[str] = mapped_column(String(30), default='transcript')
    transcript: Mapped[str] = mapped_column(Text, default='')
    segments: Mapped[list] = mapped_column(JSON, default=list)
    summary: Mapped[str] = mapped_column(Text, default='')
    decisions: Mapped[list] = mapped_column(JSON, default=list)
    topics: Mapped[list] = mapped_column(JSON, default=list)
    error: Mapped[str] = mapped_column(Text, default='')
    duration: Mapped[float] = mapped_column(default=0.0)
    audio_file: Mapped[str] = mapped_column(String(100), default='')
    original_filename: Mapped[str] = mapped_column(String(250), default='')
    tasks: Mapped[list['Task']] = relationship(cascade='all, delete-orphan', order_by='Task.position')


class Task(Base):
    __tablename__ = 'tasks'
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    meeting_id: Mapped[str] = mapped_column(ForeignKey('meetings.id'), index=True)
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


engine = create_engine(settings.database_url, connect_args={'check_same_thread': False} if settings.database_url.startswith('sqlite') else {}, pool_pre_ping=True)
Session = sessionmaker(engine, expire_on_commit=False)

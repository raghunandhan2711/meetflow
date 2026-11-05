from typing import Literal
from pydantic import BaseModel, Field, AwareDatetime


class TranscriptInput(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    transcript: str = Field(min_length=30, max_length=1000000)
    description: str = Field(default='', max_length=6000)
    meeting_at: AwareDatetime | None = None


class ActionItem(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    description: str = Field(default='', max_length=6000)
    owner: str = Field(default='Unassigned', max_length=120)
    due_date: str = Field(default='', max_length=50)
    priority: Literal['low', 'medium', 'high'] = 'medium'
    feature: str = Field(default='', max_length=120)
    evidence: str = Field(default='', max_length=3000)


class Analysis(BaseModel):
    summary: str = Field(min_length=1, max_length=12000)
    topics: list[str] = Field(default_factory=list, max_length=30)
    decisions: list[str] = Field(default_factory=list, max_length=50)
    action_items: list[ActionItem] = Field(default_factory=list, max_length=50)


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=6000)
    owner: str | None = Field(default=None, max_length=120)
    due_date: str | None = Field(default=None, max_length=50)
    priority: Literal['low', 'medium', 'high'] | None = None
    status: Literal['open', 'in_progress', 'done'] | None = None

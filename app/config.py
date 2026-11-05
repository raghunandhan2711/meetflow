from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / '.env', extra='ignore')
    database_url: str = Field(default='sqlite:///./data/meetings.db', repr=False, exclude=True)
    db_pool_size: int = Field(default=5, ge=1, le=20)
    db_max_overflow: int = Field(default=5, ge=0, le=20)
    db_pool_timeout: int = Field(default=10, ge=1, le=60)
    db_connect_timeout: int = Field(default=5, ge=1, le=30)
    groq_api_key: str = Field(default='', repr=False, exclude=True)
    groq_model: str = 'qwen/qwen3.8-27b'
    transcription_provider: str = 'local'
    whisper_model: str = 'base'
    hf_token: str = Field(default='', repr=False, exclude=True)
    diarization_enabled: bool = False
    jira_base_url: str = ''
    jira_email: str = ''
    jira_api_token: str = Field(default='', repr=False, exclude=True)
    jira_project_key: str = ''
    jira_issue_type: str = 'Task'
    jira_cloud_id: str = ''
    rate_limit_api_per_minute: int = Field(default=120, ge=1, le=10000)
    rate_limit_writes_per_minute: int = Field(default=30, ge=1, le=1000)
    rate_limit_analyses_per_minute: int = Field(default=3, ge=1, le=60)
    rate_limit_analyses_per_hour: int = Field(default=20, ge=1, le=1000)
    groq_requests_per_minute: int = Field(default=3, ge=1, le=60)
    groq_requests_per_hour: int = Field(default=20, ge=1, le=1000)

    @property
    def jira_ready(self):
        return all([self.jira_base_url, self.jira_email, self.jira_api_token, self.jira_project_key])


settings = Settings()
(ROOT / 'data' / 'uploads').mkdir(parents=True, exist_ok=True)

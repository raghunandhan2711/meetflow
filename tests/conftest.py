import pytest
from app import security


@pytest.fixture(autouse=True)
def isolated_limits(monkeypatch):
    security.api_limiter.clear()
    security.groq_limiter.clear()
    monkeypatch.setattr(security, 'provider_retry_at', 0)
    yield
    security.api_limiter.clear()
    security.groq_limiter.clear()

import logging
from concurrent.futures import ThreadPoolExecutor
import httpx
import pytest
from fastapi.testclient import TestClient
from app import main, security, services
from tests.test_api import client


def test_private_session_and_cookie_flags(client):
    client.cookies.clear()
    assert client.get('/api/settings').status_code == 401
    assert client.get('/api/meetings').status_code == 401
    client.cookies.set(security.COOKIE, 'forged-session')
    assert client.get('/api/meetings').status_code == 401
    root = client.get('/')
    assert root.status_code == 200
    assert 'HttpOnly' in root.headers['set-cookie']
    assert 'SameSite=strict' in root.headers['set-cookie']
    assert 'no-store' in root.headers['cache-control']
    assert client.get('/api/meetings').status_code == 200
    assert client.get('/api/settings').headers['cache-control'] == 'no-store'
    for path in ['/docs', '/redoc', '/openapi.json', '/.env', '/static/../.env', '/static/.env']:
        assert client.get(path).status_code == 404


def test_remote_host_and_cross_site_reads_are_rejected(client):
    assert client.get('/api/settings', headers={'Host':'attacker.example'}).status_code == 403
    assert client.get('/api/settings', headers={'Sec-Fetch-Site':'cross-site'}).status_code == 403
    assert client.get('/api/settings', headers={'Origin':'https://attacker.example'}).status_code == 403
    with TestClient(main.app, base_url='http://127.0.0.1', client=('203.0.113.10', 51000)) as remote:
        assert remote.get('/').status_code == 403
        assert remote.get('/api/health').status_code == 403


def test_api_limit_cannot_be_bypassed_with_forwarded_headers(client, monkeypatch):
    monkeypatch.setattr(main.settings, 'rate_limit_api_per_minute', 2)
    assert client.get('/api/settings').status_code == 200
    assert client.get('/api/settings').status_code == 200
    blocked = client.get('/api/settings', headers={'X-Forwarded-For':'192.0.2.5'})
    assert blocked.status_code == 429
    assert 1 <= int(blocked.headers['retry-after']) <= 60


def test_expensive_job_limit_and_provider_limit(client, monkeypatch):
    for index in range(3):
        assert client.post('/api/meetings', json={'title':f'Meeting {index}', 'transcript':'Alex: I will test the new login flow.'}).status_code == 202
    blocked = client.post('/api/meetings', json={'title':'Fourth meeting', 'transcript':'Alex: I will test the new login flow.'})
    assert blocked.status_code == 429
    assert len(client.get('/api/meetings').json()) == 3
    monkeypatch.setattr(main.settings, 'groq_requests_per_minute', 1)
    security.reserve_groq()
    with pytest.raises(ValueError, match='request limit'):
        security.reserve_groq()


def test_sliding_windows_are_atomic_and_expire():
    now = [0.0]
    limiter = security.SlidingLimiter(clock=lambda: now[0])
    rules = [('minute', 3, 60), ('hour', 4, 3600)]
    with ThreadPoolExecutor(max_workers=8) as workers:
        results = list(workers.map(lambda _: limiter.admit(rules), range(8)))
    assert results.count(0) == 3
    assert all(result == 60 for result in results if result)
    now[0] = 60
    assert limiter.admit(rules) == 0
    assert limiter.admit(rules) == 3540
    now[0] = 3600
    assert limiter.admit(rules) == 0


def test_secret_redaction_in_settings_responses_exports_and_logs(client, monkeypatch):
    secret = 'gsk_' + 'SENSITIVE' * 6
    monkeypatch.setattr(main.settings, 'groq_api_key', secret)
    assert secret not in repr(main.settings)
    assert 'groq_api_key' not in main.settings.model_dump()
    monkeypatch.setattr(services, 'analyze', lambda _: (_ for _ in ()).throw(ValueError('Provider echoed ' + secret)))
    created = client.post('/api/meetings', json={'title':'Private test', 'transcript':'Alex: Keep this credential private: '+secret})
    meeting_id = created.json()['id']
    for path in ['/api/settings', '/api/meetings', '/api/meetings/'+meeting_id,
                 f'/api/meetings/{meeting_id}/export', f'/api/meetings/{meeting_id}/report', f'/api/meetings/{meeting_id}/tasks.csv']:
        assert secret not in client.get(path).text
    invalid = client.post('/api/meetings', json={'title':secret * 5, 'transcript':'Alex: I will test the login module.'})
    assert invalid.status_code == 422
    assert secret not in invalid.text
    record = logging.LogRecord('test', logging.WARNING, '', 0, 'Header %s', (secret,), None)
    security.SecretLogFilter().filter(record)
    assert secret not in record.getMessage()


def test_expired_sessions_need_a_new_cookie():
    now = [0.0]
    sessions = security.LocalSessions(clock=lambda: now[0])
    token = sessions.issue()
    assert sessions.valid(token)
    assert token not in sessions.tokens
    now[0] = security.SESSION_TTL
    assert not sessions.valid(token)


def test_provider_429_sets_cooldown_without_leaking_body(monkeypatch):
    secret = 'gsk_' + 'PRIVATE' * 8
    monkeypatch.setattr(main.settings, 'groq_api_key', secret)
    client_type = httpx.Client
    monkeypatch.setattr(services.httpx, 'Client', lambda **kwargs: client_type(
        transport=httpx.MockTransport(lambda _: httpx.Response(429, headers={'retry-after':'120'}, text=secret)), **kwargs))
    with pytest.raises(ValueError, match='120 seconds') as error:
        services.analyze('Alex: I will fix login.')
    assert secret not in str(error.value)
    with pytest.raises(ValueError, match='request limit'):
        security.reserve_groq()

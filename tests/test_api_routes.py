"""Route inventory and end-to-end API contracts against the existing app."""
import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

from app import api, lifecycle, main, security, services, workspace
from app.schemas import ActionItem, Analysis
from tests.test_api import client


def route_inventory():
    # FastAPI versions that defer included routers keep the source APIRoutes on
    # each router, so inspect those plus the application-owned routes.
    routes = [*api.router.routes, *workspace.router.routes]
    return {(method, route.path) for route in routes for method in route.methods}


EXPECTED_ROUTES = {
    ('GET', '/api/health'), ('GET', '/api/health/live'), ('GET', '/api/settings'),
    ('GET', '/api/meetings'), ('GET', '/api/meetings/{meeting_id}'), ('GET', '/api/tasks'),
    ('POST', '/api/sample'), ('POST', '/api/meetings'), ('POST', '/api/upload'),
    ('POST', '/api/meetings/{meeting_id}/retry'), ('POST', '/api/meetings/{meeting_id}/regenerate'),
    ('PATCH', '/api/tasks/{task_id}'), ('POST', '/api/tasks/{task_id}/jira'),
    ('GET', '/api/meetings/{meeting_id}/export'), ('PATCH', '/api/meetings/{meeting_id}'),
    ('GET', '/api/meetings/{meeting_id}/audio'), ('PATCH', '/api/meetings/{meeting_id}/speakers'),
    ('POST', '/api/meetings/{meeting_id}/tasks'), ('DELETE', '/api/tasks/{task_id}'),
    ('DELETE', '/api/meetings/{meeting_id}'), ('GET', '/api/meetings/{meeting_id}/tasks.csv'),
    ('GET', '/api/meetings/{meeting_id}/report'),
}


def test_inventory_covers_every_registered_api_method():
    assert route_inventory() == EXPECTED_ROUTES


def test_every_api_route_requires_private_session(client):
    client.cookies.clear()
    for method, route in sorted(route_inventory()):
        path = route.replace('{meeting_id}', 'missing-id').replace('{task_id}', 'missing-id')
        response = client.request(method, path, json={} if method in {'POST', 'PATCH'} else None)
        expected = 200 if path in {'/api/health', '/api/health/live'} else 401
        assert response.status_code == expected, f'{method} {path}: {response.status_code} {response.text}'


def test_independent_local_sessions_share_the_single_user_workspace(client):
    saved = client.post('/api/sample').json()
    with TestClient(main.app, base_url='http://127.0.0.1', client=('127.0.0.1', 51001)) as other_session:
        assert other_session.get('/').status_code == 200
        assert other_session.get('/api/meetings/' + saved['id']).json()['id'] == saved['id']


def test_api_success_contracts_cover_every_route(client, monkeypatch):
    assert client.get('/api/health').json() == {'status': 'ok', 'application': 'ok', 'database': 'ok'}
    assert client.get('/api/health/live').json() == {'status': 'ok', 'application': 'ok'}
    settings = client.get('/api/settings').json()
    assert {'groq', 'model', 'transcription', 'diarization', 'huggingface', 'jira', 'jira_project', 'database', 'max_upload_mb'} <= settings.keys()

    analysis = Analysis(summary='The launch will move to Friday.', topics=['Launch'], decisions=['Move the launch.'],
                        action_items=[ActionItem(title='Update the plan', owner='Alex', evidence='I will update the plan.')])
    monkeypatch.setattr(main.settings, 'groq_api_key', 'test-key')
    monkeypatch.setattr(services, 'analyze', lambda _: analysis)
    created = client.post('/api/meetings', json={'title': 'Planning', 'transcript': 'Alex: I will update the plan. We agreed to move the launch to Friday.', 'description': 'Project meeting', 'meeting_at': '2026-10-13T12:00:00+05:30'})
    assert created.status_code == 202
    meeting_id = created.json()['id']
    meeting = client.get('/api/meetings/' + meeting_id)
    assert meeting.status_code == 200
    saved = meeting.json()
    assert {'id', 'title', 'transcript', 'summary', 'topics', 'decisions', 'segments', 'tasks', 'status', 'analysis_revision'} <= saved.keys()
    assert saved['status'] == 'ready' and saved['summary'] == analysis.summary
    assert client.get('/api/meetings?limit=1&offset=0&q=Planning').json()[0]['id'] == meeting_id
    assert client.get('/api/tasks?meeting_id=' + meeting_id).json()[0]['meeting_id'] == meeting_id
    assert client.patch('/api/meetings/' + meeting_id, json={'description': 'Updated', 'meeting_at': None}).status_code == 200
    assert client.post('/api/meetings/' + meeting_id + '/regenerate').status_code == 202

    sample = client.post('/api/sample')
    assert sample.status_code == 201
    sample_data = sample.json()
    speaker = sample_data['speakers'][0]
    assert client.patch('/api/meetings/' + sample_data['id'] + '/speakers', json={'speaker': speaker, 'name': 'Reviewer'}).status_code == 200

    upload_transcript = 'Recording: We agreed to ship the change after review.'
    monkeypatch.setattr(services, 'transcribe', lambda _: (upload_transcript, [{'start': 0, 'end': 5, 'speaker': 'Recording', 'text': 'We agreed to ship the change after review.'}], 5))
    uploaded = client.post('/api/upload', data={'title': 'Recorded review'}, files={'audio': ('review.wav', b'RIFF-test-audio', 'audio/wav')})
    assert uploaded.status_code == 202
    uploaded_id = uploaded.json()['id']
    assert client.get(f'/api/meetings/{uploaded_id}/audio').content == b'RIFF-test-audio'
    assert client.get(f'/api/meetings/{uploaded_id}/export').headers['content-type'].startswith('text/markdown')
    assert client.get(f'/api/meetings/{uploaded_id}/tasks.csv').headers['content-type'].startswith('text/csv')
    assert client.get(f'/api/meetings/{uploaded_id}/report').headers['content-type'].startswith('text/html')

    task = client.post(f'/api/meetings/{meeting_id}/tasks', json={'title': 'Manual follow-up'}).json()
    task_id = task['id']
    assert client.patch('/api/tasks/' + task_id, json={'owner': 'Reviewer', 'status': 'in_progress'}).status_code == 200
    monkeypatch.setattr(main.settings, 'jira_base_url', 'https://example.atlassian.net')
    monkeypatch.setattr(main.settings, 'jira_email', 'test@example.com')
    monkeypatch.setattr(main.settings, 'jira_api_token', 'test-token')
    monkeypatch.setattr(main.settings, 'jira_project_key', 'TEST')
    monkeypatch.setattr(services, 'create_jira', lambda *_: 'TEST-42')
    assert client.post(f'/api/tasks/{task_id}/jira').json()['jira_key'] == 'TEST-42'
    linked_task_id = saved['tasks'][0]['id']
    assert client.delete('/api/tasks/' + linked_task_id).status_code == 200
    assert client.delete('/api/meetings/' + uploaded_id).status_code == 200
    assert client.delete('/api/meetings/' + sample_data['id']).status_code == 200


@pytest.mark.parametrize('payload', [
    '{',
    '{"title":"Missing transcript"}',
    '{"transcript":"Missing title and long enough transcript"}',
    '{"title":"   ","transcript":"This transcript is long enough but title is blank."}',
    '{"title":"No timezone","transcript":"This transcript is long enough for this request.","meeting_at":"2026-10-13T12:00:00"}',
])
def test_malformed_and_invalid_meeting_requests_are_422(client, payload):
    response = client.post('/api/meetings', content=payload, headers={'Content-Type': 'application/json'})
    assert response.status_code == 422
    assert 'detail' in response.json()


def test_missing_identifiers_and_invalid_filters_have_expected_status(client):
    assert client.get('/api/meetings/not-a-real-id').status_code == 404
    assert client.patch('/api/meetings/not-a-real-id', json={'title': 'Missing'}).status_code == 404
    assert client.patch('/api/tasks/not-a-real-id', json={'status': 'done'}).status_code == 404
    assert client.delete('/api/tasks/not-a-real-id').status_code == 404
    assert client.delete('/api/meetings/not-a-real-id').status_code == 404
    assert client.get('/api/meetings?limit=101').status_code == 422
    assert client.get('/api/tasks?status=unknown').status_code == 422
    assert client.get('/api/tasks?limit=-1').status_code == 422


def test_sql_injection_payloads_are_bound_as_search_text(client):
    client.post('/api/sample')
    for payload in ["' OR 1=1 --", "%' UNION SELECT * FROM tasks --", "_\\'; DROP TABLE meetings; --"]:
        result = client.get('/api/meetings', params={'q': payload})
        assert result.status_code == 200
        assert isinstance(result.json(), list)
    assert len(client.get('/api/meetings').json()) == 1


def test_provider_timeout_fails_safely_and_retains_transcript(client, monkeypatch):
    monkeypatch.setattr(main.settings, 'groq_api_key', 'test-key')
    def timeout(_):
        raise httpx.ReadTimeout('provider timeout with private details')
    monkeypatch.setattr(services, 'analyze', timeout)
    response = client.post('/api/meetings', json={'title': 'Timeout', 'transcript': 'Alex: We need to review the launch plan.'})
    assert response.status_code == 202
    meeting = client.get('/api/meetings/' + response.json()['id']).json()
    assert meeting['status'] == 'failed'
    assert meeting['transcript'] == 'Alex: We need to review the launch plan.'
    assert 'private details' not in meeting['error']


def test_jira_malformed_success_response_is_reported_without_retrying(client, monkeypatch):
    monkeypatch.setattr(main.settings, 'jira_base_url', 'https://example.atlassian.net')
    monkeypatch.setattr(main.settings, 'jira_email', 'test@example.com')
    monkeypatch.setattr(main.settings, 'jira_api_token', 'test-token')
    monkeypatch.setattr(main.settings, 'jira_project_key', 'TEST')
    monkeypatch.setattr(services, 'create_jira', lambda *_: (_ for _ in ()).throw(KeyError('key')))
    task = client.post('/api/sample').json()['tasks'][0]
    path = '/api/tasks/' + task['id'] + '/jira'
    first = client.post(path)
    assert first.status_code == 502
    assert client.post(path).status_code == 409


def test_startup_migration_failure_is_reported_and_shutdown_disposes_engine(monkeypatch):
    disposed = []
    class FailingEngine:
        def dispose(self):
            disposed.append(True)
    monkeypatch.setattr(lifecycle, 'engine', FailingEngine())
    monkeypatch.setattr(lifecycle, 'migrate', lambda _: (_ for _ in ()).throw(OperationalError('private SQL', {}, Exception('password'))))
    with pytest.raises(RuntimeError, match='Database unavailable or migration failed'):
        with TestClient(main.app):
            pass
    assert disposed == [True]


def test_unexpected_route_failure_returns_generic_500_without_details(client, monkeypatch):
    class ExplodingSession:
        def __enter__(self):
            raise RuntimeError('TEST_PRIVATE_DATABASE_VALUE')
        def __exit__(self, *args):
            pass
    monkeypatch.setattr(api, 'Session', ExplodingSession)
    with TestClient(main.app, base_url='http://127.0.0.1', client=('127.0.0.1', 51002), raise_server_exceptions=False) as isolated:
        isolated.get('/')
        response = isolated.get('/api/meetings')
    assert response.status_code == 500
    assert 'TEST_PRIVATE_DATABASE_VALUE' not in response.text

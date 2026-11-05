import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app import main, services, workspace, api, pipeline, lifecycle
from app.schemas import Analysis, ActionItem


@pytest.fixture
def client(monkeypatch, tmp_path):
    (tmp_path / 'data' / 'uploads').mkdir(parents=True)
    monkeypatch.setattr(api, 'ROOT', tmp_path)
    monkeypatch.setattr(workspace, 'ROOT', tmp_path)
    engine = create_engine('sqlite://', connect_args={'check_same_thread': False}, poolclass=StaticPool)
    monkeypatch.setattr(lifecycle, 'engine', engine)
    factory = sessionmaker(engine, expire_on_commit=False)
    for module in (api, pipeline, lifecycle, workspace):
        monkeypatch.setattr(module, 'Session', factory)
    monkeypatch.setattr(main.settings, 'groq_api_key', '')
    monkeypatch.setattr(main.settings, 'jira_api_token', '')
    with TestClient(main.app, base_url='http://127.0.0.1', client=('127.0.0.1', 50000)) as client:
        assert client.get('/').status_code == 200
        yield client
    engine.dispose()


def test_sample_is_idempotent_searchable_and_exportable(client):
    first = client.post('/api/sample').json()
    assert client.post('/api/sample').json()['id'] == first['id']
    assert len(client.get('/api/meetings').json()) == 1
    assert len(client.get('/api/meetings?q=expired').json()) == 1
    assert client.get('/api/meetings?q=nonexistent').json() == []
    exported = client.get(f"/api/meetings/{first['id']}/export")
    assert '## Transcript' in exported.text
    assert 'attachment' in exported.headers['content-disposition']
    assert first['source'] == 'sample'


def test_task_edit_persists_and_validates(client):
    m = client.post('/api/sample').json()
    task = m['tasks'][0]
    edited = client.patch('/api/tasks/'+task['id'], json={'owner':'New owner','status':'done'})
    assert edited.status_code == 200
    assert client.get('/api/meetings/'+m['id']).json()['tasks'][0]['owner'] == 'New owner'
    assert client.patch('/api/tasks/'+task['id'], json={'priority':'urgent'}).status_code == 422
    assert client.post('/api/tasks/'+task['id']+'/jira').status_code == 409


def test_missing_key_preserves_transcript_and_retry_works(client, monkeypatch):
    monkeypatch.setattr(main.settings, 'rate_limit_analyses_per_minute', 10)
    transcript = 'Alex: I will fix the login issue by Friday. We agreed to delay the release.'
    res = client.post('/api/meetings', json={'title':'Planning','transcript':transcript})
    assert res.status_code == 202
    mid = res.json()['id']
    failed = client.get('/api/meetings/'+mid).json()
    assert failed['status'] == 'transcribed'
    assert failed['transcript'] == transcript
    assert 'Groq' in failed['error']
    assert client.post(f'/api/meetings/{mid}/retry').status_code == 409
    monkeypatch.setattr(main.settings, 'groq_api_key', 'test-key')
    monkeypatch.setattr(services, 'analyze', lambda _: Analysis(summary='Release delayed.',decisions=['Delay release.'],action_items=[ActionItem(title='Fix login',owner='Alex')]))
    assert client.post(f'/api/meetings/{mid}/retry').status_code == 202
    complete = client.get('/api/meetings/'+mid).json()
    assert complete['status'] == 'ready'
    assert complete['tasks'][0]['owner'] == 'Alex'
    assert client.post(f'/api/meetings/{mid}/retry').status_code == 409


def test_upload_validation_and_processing(client, monkeypatch):
    monkeypatch.setattr(main.settings, 'groq_api_key', 'test-key')
    assert client.post('/api/upload', data={'title':'Test'}, files={'audio':('test.exe',b'bad')}).status_code == 415
    assert client.post('/api/upload', data={'title':'Test'}, files={'audio':('test.wav',b'')}).status_code == 422
    monkeypatch.setattr(services, 'transcribe', lambda _: ('Alex: We agreed to test the release.', [{'start':0,'end':4,'speaker':'Alex','text':'We agreed to test the release.'}], 4))
    monkeypatch.setattr(services, 'analyze', lambda _: Analysis(summary='The team will test the release.'))
    res = client.post('/api/upload', data={'title':'Audio test'}, files={'audio':('test.wav',b'fake audio handled by mocked transcription')})
    assert res.status_code == 202
    m = client.get('/api/meetings/'+res.json()['id']).json()
    assert m['status'] == 'ready'
    assert m['speakers'] == ['Alex']
    assert m['duration'] == 4


def configure_jira(monkeypatch):
    for field,value in [('jira_base_url','https://example.atlassian.net'),('jira_email','test@example.com'),('jira_api_token','test'),('jira_project_key','TEST')]:
        monkeypatch.setattr(main.settings, field, value)


def test_jira_success_is_not_duplicated(client, monkeypatch):
    configure_jira(monkeypatch)
    calls = []
    def create(task, meeting):
        calls.append(task.id)
        return 'TEST-1'
    monkeypatch.setattr(services, 'create_jira', create)
    t = client.post('/api/sample').json()['tasks'][0]
    path = '/api/tasks/'+t['id']+'/jira'
    assert client.post(path).json()['jira_key'] == 'TEST-1'
    assert client.post(path).json()['jira_key'] == 'TEST-1'
    assert len(calls) == 1
    assert client.patch('/api/tasks/'+t['id'],json={'title':'Changed'}).status_code == 409


def test_uncertain_jira_delivery_blocks_retry(client, monkeypatch):
    configure_jira(monkeypatch)
    def fail(*args):
        raise TimeoutError('network timeout')
    monkeypatch.setattr(services, 'create_jira', fail)
    t = client.post('/api/sample').json()['tasks'][0]
    path = '/api/tasks/'+t['id']+'/jira'
    assert client.post(path).status_code == 502
    assert client.post(path).status_code == 409


def test_cross_origin_and_input_validation(client):
    assert client.post('/api/sample',headers={'Origin':'https://attacker.example'}).status_code == 403
    assert client.post('/api/meetings',json={'title':' ','transcript':' '*35}).status_code == 422
    assert client.get('/api/meetings/missing').status_code == 404
    settings = client.get('/api/settings').json()
    assert 'groq_api_key' not in settings and 'jira_api_token' not in settings


def test_speaker_alignment_uses_overlap():
    segments = [{'start':0,'end':3},{'start':4,'end':8},{'start':12,'end':13}]
    aligned = services.align_speakers(segments,[(0,4,'Speaker 1'),(4,9,'Speaker 2')])
    assert [s['speaker'] for s in aligned] == ['Speaker 1','Speaker 2','Unknown']


def test_request_size_limits_before_parsing(client):
    response = client.post('/api/meetings', content=b'x', headers={'Content-Length': str(5 * 1024 * 1024), 'Content-Type':'application/json'})
    assert response.status_code == 413
    response = client.post('/api/meetings', content=iter([b'x' * (1024 * 1024)] * 5), headers={'Content-Type':'application/json'})
    assert response.status_code == 413

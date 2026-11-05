"""Explicitly opted-in PostgreSQL tests with schema-scoped cleanup only."""
import os
from uuid import uuid4
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text, inspect, select
from sqlalchemy.schema import CreateSchema, DropSchema
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError
from app.database import make_engine, Meeting, Task
from app.migrations import migrate, initial, migration_status
from app import api, pipeline, lifecycle, workspace, main, services, security
from app.schemas import Analysis, ActionItem

pytestmark = pytest.mark.skipif(not os.environ.get('MEETFLOW_TEST_DATABASE_URL'), reason='Use npm run test:postgres for isolated PostgreSQL integration tests.')


@pytest.fixture
def pg_engine():
    url = os.environ['MEETFLOW_TEST_DATABASE_URL']
    assert url.startswith('postgresql')
    admin = make_engine(url)
    schema = 'meetflow_test_' + uuid4().hex
    with admin.begin() as connection:
        connection.execute(CreateSchema(schema))
    engine = make_engine(url, connect_args={'connect_timeout': 5,
        'options': '-c search_path=' + schema + ' -c statement_timeout=30000 -c lock_timeout=10000'})
    try:
        yield engine
    finally:
        engine.dispose()
        # The generated name is never supplied by a user/environment variable.
        assert schema.startswith('meetflow_test_') and len(schema) == 46
        with admin.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        admin.dispose()


@pytest.fixture
def pg_app(pg_engine, monkeypatch, tmp_path):
    factory = sessionmaker(pg_engine, expire_on_commit=False)
    monkeypatch.setattr(lifecycle, 'engine', pg_engine)
    for module in (api, pipeline, lifecycle, workspace):
        monkeypatch.setattr(module, 'Session', factory)
    for module in (api, workspace):
        monkeypatch.setattr(module, 'ROOT', tmp_path)
    (tmp_path / 'data/uploads').mkdir(parents=True)
    monkeypatch.setattr(main.settings, 'groq_api_key', 'test-key')
    monkeypatch.setattr(main.settings, 'jira_api_token', '')
    monkeypatch.setattr(main.settings, 'rate_limit_analyses_per_minute', 30)
    monkeypatch.setattr(main.settings, 'rate_limit_analyses_per_hour', 100)
    monkeypatch.setattr(services, 'analyze', lambda _: Analysis(summary='The release is delayed.', decisions=['Delay release.'], topics=['Release'], action_items=[ActionItem(title='Fix login', owner='Alex', evidence='I will fix login.')]))
    return factory


def browser():
    return TestClient(main.app, base_url='http://127.0.0.1', client=('127.0.0.1', 51000))


def test_migrations_constraints_types_and_rollback(pg_engine):
    assert migrate(pg_engine) == ['001_initial', '002_integrity_metadata']
    assert migrate(pg_engine) == []
    assert all(item['applied'] for item in migration_status(pg_engine))
    columns = {c['name']: str(c['type']) for c in inspect(pg_engine).get_columns('meetings')}
    assert columns['segments'] == 'JSONB'
    assert inspect(pg_engine).get_columns('meetings')[2]['type'].timezone
    factory = sessionmaker(pg_engine, expire_on_commit=False)
    with factory() as db:
        db.add(Task(meeting_id=str(uuid4()), title='Orphan'))
        with pytest.raises(IntegrityError): db.commit()
        db.rollback()
        m = Meeting(title='Will roll back')
        db.add(m)
        db.flush()
        mid = m.id
        db.add(Task(meeting_id=mid, title='Invalid status', status='bad'))
        with pytest.raises(IntegrityError): db.commit()
        db.rollback()
        assert db.get(Meeting, mid) is None
        m = Meeting(title='Protected by FK')
        m.tasks = [Task(title='Keep linked')]
        db.add(m); db.commit()
        with pytest.raises(IntegrityError):
            db.execute(text('DELETE FROM meetings WHERE id = :id'), {'id': m.id})
            db.commit()
        db.rollback()
        assert db.get(Meeting, m.id) is not None


def test_legacy_upgrade_preserves_identifiers_and_content(pg_engine):
    with pg_engine.begin() as connection:
        initial(connection)
        connection.execute(text("INSERT INTO meetings (id,title,transcript,summary) VALUES (:id,'Legacy',:transcript,'Saved summary')"), {'id': 'old-meeting', 'transcript': 'Original transcript ' * 8000})
        connection.execute(text("INSERT INTO tasks (id,meeting_id,title,jira_key) VALUES ('old-task','old-meeting','Saved task','SCRUM-1')"))
    migrate(pg_engine)
    with sessionmaker(pg_engine)() as db:
        m = db.get(Meeting, 'old-meeting')
        assert m.transcript == 'Original transcript ' * 8000
        assert m.summary == 'Saved summary' and m.updated_at is not None
        assert m.tasks[0].id == 'old-task' and m.tasks[0].jira_key == 'SCRUM-1'
        assert m.tasks[0].created_at is not None


def test_migration_failure_rolls_back_the_whole_upgrade(pg_engine, monkeypatch):
    from app import migrations
    def fail(connection):
        connection.execute(text('CREATE TABLE migration_probe (id INTEGER)'))
        raise RuntimeError('Injected migration failure')
    monkeypatch.setattr(migrations, 'MIGRATIONS', [('001_initial', initial), ('002_failure', fail)])
    with pytest.raises(RuntimeError, match='Injected'):
        migrate(pg_engine)
    assert inspect(pg_engine).get_table_names() == []


def test_full_workflow_restart_regeneration_and_failed_generation(pg_app, monkeypatch):
    with browser() as client:
        client.get('/')
        response = client.post('/api/meetings', json={'title':'Planning','transcript':'Alex: I will fix login. We agreed to delay the release.','description':'Sprint plan','meeting_at':'2026-10-10T10:00:00+05:30'})
        assert response.status_code == 202
        mid = response.json()['id']
        first = client.get('/api/meetings/'+mid).json()
        assert first['status'] == 'ready' and first['analysis_revision'] == 1
        tid = first['tasks'][0]['id']
        assert client.patch('/api/tasks/'+tid, json={'owner':'Reviewer','status':'done'}).status_code == 200
        filtered = client.get('/api/tasks', params={'meeting_id':mid,'status':'done','owner':'Reviewer','limit':1}).json()
        assert len(filtered) == 1 and filtered[0]['id'] == tid
        assert client.get('/api/tasks', params={'status':'open','meeting_id':mid}).json() == []
        assert client.get('/api/tasks?status=invalid').status_code == 422
        assert client.post(f'/api/meetings/{mid}/regenerate').status_code == 202
        second = client.get('/api/meetings/'+mid).json()
        assert len(second['tasks']) == 1 and second['tasks'][0]['id'] == tid
        assert second['tasks'][0]['owner'] == 'Reviewer' and second['analysis_revision'] == 2
    # New lifespan / pooled connections, same PostgreSQL records.
    with browser() as restarted:
        restarted.get('/app')
        saved = restarted.get('/api/meetings/'+mid).json()
        assert saved['transcript'] == first['transcript'] and saved['summary'] == first['summary']
        assert saved['tasks'][0]['status'] == 'done'
        assert saved['description'] == 'Sprint plan' and saved['meeting_at']
        def fail(_): raise ValueError('Provider unavailable')
        monkeypatch.setattr(services, 'analyze', fail)
        assert restarted.post(f'/api/meetings/{mid}/regenerate').status_code == 202
        failed = restarted.get('/api/meetings/'+mid).json()
        assert failed['status'] == 'failed' and failed['summary'] == saved['summary']
        assert failed['analysis_revision'] == 2 and failed['tasks'][0]['id'] == tid


def test_duplicate_workers_claim_once(pg_app, monkeypatch):
    migrate(pg_app.kw['bind'])
    with pg_app() as db:
        m = Meeting(title='Claim', transcript='Alex: I will fix login.')
        db.add(m); db.commit(); mid = m.id
    calls = []
    monkeypatch.setattr(services, 'analyze', lambda _: (calls.append(1) or Analysis(summary='Done', action_items=[ActionItem(title='Fix login'), ActionItem(title='Fix login')])))
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(pipeline.process_meeting, [mid, mid]))
    assert len(calls) == 1
    with pg_app() as db:
        m = db.get(Meeting, mid)
        assert len(m.tasks) == 1 and m.status == 'ready'


def test_concurrent_sample_requests_create_one_meeting(pg_app):
    from concurrent.futures import ThreadPoolExecutor
    with browser() as first, browser() as second:
        first.get('/')
        second.get('/')
        with ThreadPoolExecutor(max_workers=2) as workers:
            responses = list(workers.map(lambda client: client.post('/api/sample'), (first, second)))
    assert [response.status_code for response in responses] == [201, 201]
    assert responses[0].json()['id'] == responses[1].json()['id']
    with pg_app() as db:
        assert db.query(Meeting).filter(Meeting.source == 'sample').count() == 1


def test_commit_failure_keeps_previous_results(pg_app, monkeypatch):
    from sqlalchemy import event
    with browser() as client:
        client.get('/')
        mid = client.post('/api/meetings', json={'title':'Atomic','transcript':'Alex: I will fix login. We agreed to delay release.'}).json()['id']
        old = client.get('/api/meetings/'+mid).json()
        monkeypatch.setattr(services, 'analyze', lambda _: Analysis(summary='New output',action_items=[ActionItem(title='New task')]))
        def reject_new_task(mapper, connection, target):
            if target.title == 'New task': raise RuntimeError('Injected transaction failure')
        event.listen(Task, 'before_insert', reject_new_task)
        try:
            assert client.post(f'/api/meetings/{mid}/regenerate').status_code == 202
        finally:
            event.remove(Task, 'before_insert', reject_new_task)
        saved = client.get('/api/meetings/'+mid).json()
        assert saved['status'] == 'failed'
        assert saved['summary'] == old['summary'] and saved['analysis_revision'] == old['analysis_revision']
        assert [t['id'] for t in saved['tasks']] == [t['id'] for t in old['tasks']]


def test_large_transcript_pagination_validation_and_auth(pg_app):
    with browser() as client:
        assert client.get('/api/meetings').status_code == 401
        client.get('/')
        transcript = 'Alex: an extended meeting discussion. ' * 4000
        mid = client.post('/api/meetings', json={'title':'Long meeting','transcript':transcript}).json()['id']
        saved = client.get('/api/meetings/'+mid).json()
        assert saved['transcript'] == transcript.strip() and saved['status'] == 'transcribed'
        assert client.get('/api/meetings?limit=1').json()[0]['id'] == mid
        assert client.get('/api/meetings?limit=1&offset=1').json() == []
        assert client.get('/api/meetings?limit=1000').status_code == 422
        assert client.get('/api/meetings?q=%27%20OR%201%3D1--').json() == []
        assert client.patch('/api/tasks/missing', json={'status':'done'}).status_code == 404
        assert client.patch('/api/meetings/'+mid, json={'meeting_at':'2026-10-10T10:00:00'}).status_code == 422
        assert client.get('/api/health/live').status_code == 200


def test_database_failures_are_safe(pg_app, monkeypatch):
    from sqlalchemy.exc import OperationalError
    class BrokenSession:
        def __enter__(self): raise OperationalError('secret SQL', {}, Exception('private credential'))
        def __exit__(self, *args): pass
    with browser() as client:
        client.get('/')
        monkeypatch.setattr(api, 'Session', BrokenSession)
        health = client.get('/api/health')
        assert health.status_code == 503 and health.json()['database'] == 'unavailable'
        assert client.get('/api/health/live').status_code == 200
        response = client.get('/api/meetings')
        assert response.status_code == 503
        assert 'private credential' not in response.text and 'secret SQL' not in response.text

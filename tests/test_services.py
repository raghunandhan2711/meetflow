import json
from types import SimpleNamespace
import httpx
import pytest
from app import services


def mock_http(monkeypatch, handler):
    client_type = httpx.Client
    monkeypatch.setattr(services.httpx, 'Client', lambda **kwargs: client_type(transport=httpx.MockTransport(handler), **kwargs))


def test_groq_contract_and_unverified_quotes(monkeypatch):
    monkeypatch.setattr(services.settings, 'groq_api_key', 'test-key')
    def handler(request):
        assert request.url.host == 'api.groq.com'
        body = json.loads(request.content)
        assert body['response_format'] == {'type':'json_object'}
        assert request.headers['authorization'] == 'Bearer test-key'
        result = {'summary':'Fix the login bug.', 'decisions':[], 'topics':['Authentication'], 'action_items':[{'title':'Fix login','evidence':'A fabricated quote'}]}
        return httpx.Response(200, json={'choices':[{'message':{'content':json.dumps(result)}}]})
    mock_http(monkeypatch, handler)
    result = services.analyze('Alex: I will fix the login bug.')
    assert result.action_items[0].evidence == ''


def test_groq_rejects_malformed_result(monkeypatch):
    monkeypatch.setattr(services.settings, 'groq_api_key', 'test-key')
    mock_http(monkeypatch, lambda _: httpx.Response(200,json={'choices':[{'message':{'content':'not JSON'}}]}))
    with pytest.raises(ValueError, match='required format'):
        services.analyze('Alex: I will fix the login bug.')


@pytest.mark.parametrize('handler, message', [
    (lambda _: httpx.Response(503, text='provider internal body'), 'HTTP 503'),
    (lambda _: httpx.Response(200, json={'choices': []}), 'required format'),
    (lambda _: httpx.Response(200, json={'choices': [{'message': {'content': '{broken'}}]}), 'required format'),
])
def test_groq_provider_error_contract_is_safe(monkeypatch, handler, message):
    monkeypatch.setattr(services.settings, 'groq_api_key', 'test-key')
    mock_http(monkeypatch, handler)
    with pytest.raises(ValueError, match=message) as error:
        services.analyze('Alex: I will review the launch plan.')
    assert 'provider internal body' not in str(error.value)


def test_groq_timeout_is_not_converted_to_a_success(monkeypatch):
    monkeypatch.setattr(services.settings, 'groq_api_key', 'test-key')
    client_type = httpx.Client
    def timeout(**kwargs):
        return client_type(transport=httpx.MockTransport(lambda _: (_ for _ in ()).throw(httpx.ReadTimeout('private provider details'))), **kwargs)
    monkeypatch.setattr(services.httpx, 'Client', timeout)
    with pytest.raises(httpx.ReadTimeout):
        services.analyze('Alex: I will review the launch plan.')


def test_groq_missing_key_fails_before_network(monkeypatch):
    monkeypatch.setattr(services.settings, 'groq_api_key', '')
    with pytest.raises(ValueError, match='GROQ_API_KEY'):
        services.analyze('Alex: I will review the launch plan.')


def test_groq_transcription_contract_and_safe_provider_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(services.settings, 'groq_api_key', 'test-key')
    monkeypatch.setattr(services.settings, 'transcription_provider', 'groq')
    path = tmp_path / 'meeting.wav'
    path.write_bytes(b'fake audio')
    real_client = httpx.Client
    def transcription(request):
        assert request.url.path.endswith('/audio/transcriptions')
        assert request.headers['authorization'] == 'Bearer test-key'
        return httpx.Response(200, json={'duration': 3, 'segments': [{'start': 0, 'end': 3, 'text': 'We agreed to review the release.'}]})
    monkeypatch.setattr(services.httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(transcription), **kwargs))
    transcript, segments, duration = services.transcribe(path)
    assert transcript == 'We agreed to review the release.'
    assert segments[0]['start'] == 0 and duration == 3

    monkeypatch.setattr(services.httpx, 'Client', lambda **kwargs: real_client(transport=httpx.MockTransport(lambda _: httpx.Response(401, text='sensitive provider body')), **kwargs))
    with pytest.raises(ValueError, match='HTTP 401') as error:
        services.transcribe(path)
    assert 'sensitive provider body' not in str(error.value)


def test_transcription_without_key_and_invalid_provider_fail_cleanly(monkeypatch, tmp_path):
    path = tmp_path / 'meeting.wav'
    path.write_bytes(b'audio')
    monkeypatch.setattr(services.settings, 'transcription_provider', 'groq')
    monkeypatch.setattr(services.settings, 'groq_api_key', '')
    with pytest.raises(ValueError, match='GROQ_API_KEY'):
        services.transcribe(path)
    monkeypatch.setattr(services.settings, 'transcription_provider', 'unknown')
    with pytest.raises(ValueError, match='TRANSCRIPTION_PROVIDER'):
        services.transcribe(path)


def test_jira_payload_contains_context_and_trace_label(monkeypatch):
    for key, value in {'jira_base_url':'https://example.atlassian.net','jira_email':'user@example.com','jira_api_token':'token','jira_project_key':'ENG','jira_cloud_id':''}.items():
        monkeypatch.setattr(services.settings,key,value)
    def handler(request):
        assert str(request.url) == 'https://example.atlassian.net/rest/api/3/issue'
        fields = json.loads(request.content)['fields']
        assert fields['project']['key'] == 'ENG'
        assert fields['description']['type'] == 'doc'
        assert 'minutes-task-123' in fields['labels']
        assert 'assignee' not in fields
        return httpx.Response(201,json={'key':'ENG-12'})
    mock_http(monkeypatch, handler)
    task = SimpleNamespace(id='task-123',title='Fix login',description='Fix refresh flow.',owner='Alex',due_date='Friday',feature='Auth',evidence='I will fix login.')
    assert services.create_jira(task,SimpleNamespace(title='Planning')) == 'ENG-12'

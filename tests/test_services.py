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

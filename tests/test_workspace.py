from pathlib import Path
from app import main, workspace, services
from app.schemas import Analysis, ActionItem
from tests.test_api import client


def test_speaker_correction_and_report(client):
    meeting = client.post('/api/sample').json()
    result = client.patch(f"/api/meetings/{meeting['id']}/speakers",json={'speaker':'Raghunandhan','name':'Raghu'})
    assert result.status_code == 200
    updated = client.get('/api/meetings/'+meeting['id']).json()
    assert 'Raghu' in updated['speakers']
    assert updated['tasks'][0]['owner'] == 'Raghu'
    assert 'Raghu:' in updated['transcript']
    assert client.get(f"/api/meetings/{meeting['id']}/report").status_code == 200
    assert 'Full transcript' in client.get(f"/api/meetings/{meeting['id']}/report").text
    assert client.patch(f"/api/meetings/{meeting['id']}/speakers",json={'speaker':'Nishan','name':'Raghu'}).status_code == 409


def test_manual_tasks_and_csv_are_safe(client):
    meeting = client.post('/api/sample').json()
    result = client.post(f"/api/meetings/{meeting['id']}/tasks",json={'title':'=HYPERLINK("bad")','description':'Check the release.'})
    assert result.status_code == 201
    task_id = result.json()['id']
    assert client.patch('/api/tasks/'+task_id,json={'status':'in_progress'}).status_code == 200
    csv = client.get(f"/api/meetings/{meeting['id']}/tasks.csv")
    assert "'=HYPERLINK" in csv.text
    assert client.delete('/api/tasks/'+task_id).status_code == 200
    assert len(client.get('/api/meetings/'+meeting['id']).json()['tasks']) == 3


def test_audio_is_retained_and_removed_with_meeting(client,monkeypatch):
    monkeypatch.setattr(services,'transcribe',lambda _: ('Speaker: Welcome to our engineering meeting.',[],5))
    recording = b'RIFF-test-recording'
    meeting = client.post('/api/upload',data={'title':'Recording'},files={'audio':('meeting.wav',recording)}).json()
    audio = client.get(f"/api/meetings/{meeting['id']}/audio")
    assert audio.content == recording
    assert client.get('/api/meetings/'+meeting['id']).json()['has_audio']
    assert client.delete('/api/meetings/'+meeting['id']).status_code == 200
    assert client.get(f"/api/meetings/{meeting['id']}/audio").status_code == 404


def test_manual_tasks_survive_analysis(client,monkeypatch):
    meeting = client.post('/api/meetings',json={'title':'Planning','transcript':'Alex: I will fix the login bug by Friday.'}).json()
    manual = client.post(f"/api/meetings/{meeting['id']}/tasks",json={'title':'Manually reviewed task'}).json()
    monkeypatch.setattr(main.settings,'groq_api_key','test-key')
    monkeypatch.setattr(services,'analyze',lambda _: Analysis(summary='Login fix.',action_items=[ActionItem(title='Fix login')]))
    assert client.post(f"/api/meetings/{meeting['id']}/retry").status_code == 202
    tasks = client.get('/api/meetings/'+meeting['id']).json()['tasks']
    assert len(tasks) == 2
    assert tasks[0]['id'] == manual['id']


def test_report_escapes_user_content(client):
    meeting = client.post('/api/sample').json()
    client.patch('/api/meetings/'+meeting['id'],json={'title':'<script>alert(1)</script>'})
    report = client.get(f"/api/meetings/{meeting['id']}/report")
    assert '<script>' not in report.text
    assert '&lt;script&gt;' in report.text

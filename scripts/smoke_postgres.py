"""Check the running PostgreSQL-backed website using a disposable meeting."""
import time
from pathlib import Path
import httpx

ROOT = Path(__file__).resolve().parent.parent
with httpx.Client(base_url='http://127.0.0.1:8000', timeout=30) as client:
    client.get('/').raise_for_status()
    assert client.get('/api/health').json()['status'] == 'ok'
    assert client.get('/api/settings').json()['database'] == 'PostgreSQL'
    meeting_id = None
    try:
        with (ROOT / 'tests' / 'fixtures' / 'meeting.wav').open('rb') as audio:
            response = client.post('/api/upload', data={'title':'Verification: local speech and PostgreSQL'},
                                   files={'audio':('meeting.wav', audio, 'audio/wav')})
        response.raise_for_status()
        meeting_id = response.json()['id']
        for attempt in range(120):
            meeting = client.get('/api/meetings/' + meeting_id).json()
            if meeting['status'] not in ('queued','transcribing','analyzing'):
                break
            time.sleep(.5)
        assert meeting['status'] in ('transcribed','ready'), meeting['error']
        assert 'login' in meeting['transcript'].lower()
        assert meeting['has_audio'] and len(meeting['segments']) > 0
        assert client.get(f'/api/meetings/{meeting_id}/audio').content[:4] == b'RIFF'
        task = client.post(f'/api/meetings/{meeting_id}/tasks', json={'title':'Verify meeting persistence','owner':'Reviewer'})
        task.raise_for_status()
        task_id = task.json()['id']
        client.patch('/api/tasks/' + task_id, json={'status':'in_progress'}).raise_for_status()
        persisted = client.get('/api/meetings/' + meeting_id).json()['tasks']
        assert next(task for task in persisted if task['id'] == task_id)['status'] == 'in_progress'
        assert client.get(f'/api/meetings/{meeting_id}/tasks.csv').status_code == 200
        assert client.get(f'/api/meetings/{meeting_id}/report').status_code == 200
        print('PostgreSQL website verified: real audio transcription, timestamps, playback, persisted tasks, CSV and report.')
    finally:
        if meeting_id:
            client.delete('/api/meetings/' + meeting_id).raise_for_status()
            assert client.get('/api/meetings/' + meeting_id).status_code == 404

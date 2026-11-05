"""Real audio + Groq + PostgreSQL + process restart, in a disposable test schema.

Uses one provider request. Deletes only its own test meeting/schema, never public data.
"""
import os
from pathlib import Path
import subprocess
import sys
import time
from uuid import uuid4
import httpx
from sqlalchemy.schema import CreateSchema, DropSchema

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.config import settings
from app.database import make_engine


def main():
    if not settings.database_url.startswith('postgresql') or not settings.groq_api_key:
        raise RuntimeError('Configure local PostgreSQL and Groq before running live verification.')
    # Check before allocating test resources; never exercise another running app.
    import socket
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 8131))
    admin = make_engine(settings.database_url)
    schema = 'meetflow_test_' + uuid4().hex
    with admin.begin() as connection:
        connection.execute(CreateSchema(schema))
    url = admin.url.update_query_dict({'options': '-c search_path=' + schema})
    env = {**os.environ, 'DATABASE_URL': url.render_as_string(hide_password=False), 'JIRA_API_TOKEN': '',
           'TRANSCRIPTION_PROVIDER': 'local', 'DIARIZATION_ENABLED': 'false'}
    (ROOT / 'artifacts').mkdir(exist_ok=True)
    output = (ROOT / 'artifacts' / (schema + '.log')).open('w', encoding='utf-8')
    process = None
    mid = None
    base = 'http://127.0.0.1:8131'

    def start_server():
        child = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8131', '--no-access-log'],
                                 cwd=ROOT, env=env, stdout=output, stderr=output,
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        try:
            for _ in range(100):
                if child.poll() is not None:
                    raise RuntimeError('Verification server failed to start; inspect its ignored artifact log.')
                try:
                    if httpx.get(base + '/api/health', timeout=1, trust_env=False).status_code == 200:
                        return child
                except httpx.RequestError:
                    pass
                time.sleep(.2)
            raise RuntimeError('Verification server startup timed out.')
        except Exception:
            child.terminate(); child.wait(timeout=15)
            raise

    try:
        process = start_server()
        with httpx.Client(base_url=base, timeout=30, trust_env=False) as client:
            client.get('/').raise_for_status()
            with (ROOT / 'tests/fixtures/meeting.wav').open('rb') as recording:
                response = client.post('/api/upload', data={'title':'Isolated live persistence verification'}, files={'audio':('meeting.wav',recording,'audio/wav')})
            response.raise_for_status()
            mid = response.json()['id']
            for _ in range(180):
                response = client.get('/api/meetings/' + mid)
                response.raise_for_status()
                saved = response.json()
                if saved['status'] not in ('queued','transcribing','analyzing'):
                    break
                time.sleep(1)
            assert saved['status'] == 'ready', 'Live processing did not complete; inspect the saved test status.'
            assert saved['transcript'] and saved['segments'] and saved['summary'] and saved['tasks']
            tid = saved['tasks'][0]['id']
            client.patch('/api/tasks/' + tid, json={'status':'in_progress','owner':'Persistence reviewer'}).raise_for_status()
            saved = client.get('/api/meetings/' + mid).json()
            process.terminate(); process.wait(timeout=15)
            process = start_server()
            client.get('/app').raise_for_status()
            restored = client.get('/api/meetings/' + mid)
            restored.raise_for_status()
            restored = restored.json()
            assert restored == saved, 'Saved meeting changed across process restart.'
            assert client.get(f'/api/meetings/{mid}/audio').content[:4] == b'RIFF'
            client.get(f'/api/meetings/{mid}/tasks.csv').raise_for_status()
            client.get(f'/api/meetings/{mid}/report').raise_for_status()
            client.delete('/api/meetings/' + mid).raise_for_status()
            mid = None
        print('Live PostgreSQL verification passed: real Whisper audio, real Groq summary/decisions/tasks, task edit, audio playback, exports, and identical data after stopping/restarting the server.')
    finally:
        if process and process.poll() is None:
            if mid:
                try:
                    with httpx.Client(base_url=base, timeout=10, trust_env=False) as cleanup:
                        cleanup.get('/')
                        cleanup.delete('/api/meetings/' + mid).raise_for_status()
                except httpx.HTTPError:
                    print('Test upload cleanup unavailable; any remaining file is confined to data/uploads.')
            process.terminate(); process.wait(timeout=15)
        output.close()
        assert schema.startswith('meetflow_test_') and len(schema) == 46
        with admin.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        admin.dispose()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('Live verification failed (' + type(error).__name__ + '). Credentials and response bodies withheld.', file=sys.stderr)
        raise SystemExit(1)

"""Start the project database and website together."""
import os
import socket
from pathlib import Path
from dotenv import dotenv_values
import httpx
import uvicorn

ROOT = Path(__file__).resolve().parent
WEBSITE = 'http://127.0.0.1:8000'


def meetflow_is_running():
    """Recognize our app without mistaking another service for MeetFlow."""
    try:
        with httpx.Client(base_url=WEBSITE, timeout=3, trust_env=False) as client:
            page = client.get('/app')
            health = client.get('/api/health')
            return (page.status_code == 200
                    and 'AI-Powered Meeting Analysis &amp; Task Automation System' in page.text
                    and '/static/workspace.js' in page.text
                    and health.status_code == 200
                    and health.json().get('status') == 'ok')
    except (httpx.RequestError, ValueError, AttributeError):
        return False


def main():
    os.chdir(ROOT)
    # Reserve the port before initializing the database or recovering jobs.
    # Pass this same socket to Uvicorn to avoid a check-then-bind race.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        if os.name == 'nt':
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        try:
            listener.bind(('127.0.0.1', 8000))
        except OSError as error:
            if error.errno not in (98, 10048) and getattr(error, 'winerror', None) != 10048:
                raise
            if meetflow_is_running():
                print(f'MeetFlow is already running. Open {WEBSITE}')
                print(f'Workspace: {WEBSITE}/app')
                print('No second server was started. You can close this terminal.')
                return 0
            print('Port 8000 is occupied by another service or an unresponsive MeetFlow instance.')
            print('Stop the program using that port, then run npm run dev again.')
            return 1

        configuration = dotenv_values(ROOT / '.env')
        url = configuration.get('DATABASE_URL', '')
        if '@127.0.0.1:55432/minutes' in url:
            from scripts.manage_postgres import start
            if not start():
                raise RuntimeError('The project database is not initialized. Run scripts/manage_postgres.py initialize.')

        print(f'Website: {WEBSITE}')
        print(f'Workspace: {WEBSITE}/app')
        print('Keep this terminal open. Press Ctrl+C to stop the website.', flush=True)
        listener.listen(128)
        config = uvicorn.Config('app.main:app', host='127.0.0.1', port=8000,
                                access_log=False, proxy_headers=False)
        uvicorn.Server(config).run(sockets=[listener])
    return 0

if __name__ == '__main__':
    raise SystemExit(main())

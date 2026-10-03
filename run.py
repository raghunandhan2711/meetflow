"""Start the project database and website together."""
import os
from pathlib import Path
from dotenv import dotenv_values
import uvicorn

ROOT = Path(__file__).resolve().parent
os.chdir(ROOT)
configuration = dotenv_values(ROOT / '.env')
url = configuration.get('DATABASE_URL','')
if '@127.0.0.1:55432/minutes' in url:
    from scripts.manage_postgres import start
    if not start():
        raise RuntimeError('The project database is not initialized. Run scripts/manage_postgres.py initialize.')

if __name__ == '__main__':
    print('Website: http://127.0.0.1:8000')
    uvicorn.run('app.main:app',host='127.0.0.1',port=8000,access_log=False,proxy_headers=False)

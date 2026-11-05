"""Run integration tests in random isolated schemas, never in public tables."""
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app.config import settings

def main():
    if not settings.database_url.startswith('postgresql'):
        raise SystemExit('Set DATABASE_URL to local PostgreSQL before running this test command.')
    environment = {**os.environ, 'MEETFLOW_TEST_DATABASE_URL': settings.database_url,
                   'GROQ_API_KEY': '', 'JIRA_API_TOKEN': ''}
    temporary = ROOT / 'artifacts' / ('pytest-postgres-' + uuid4().hex)
    result = subprocess.run([sys.executable, '-m', 'pytest', '-q', 'tests/test_postgres.py',
                             '-p', 'no:cacheprovider', '--basetemp', str(temporary), '--tb=short'],
                            cwd=ROOT, env=environment)
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())

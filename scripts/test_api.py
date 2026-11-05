"""Run all API tests with PostgreSQL tests isolated in disposable schemas."""
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def main():
    from sqlalchemy import text
    from sqlalchemy.exc import SQLAlchemyError
    from app.config import settings
    from app.database import engine

    if engine.dialect.name != 'postgresql':
        print('API integration suite requires DATABASE_URL configured for local PostgreSQL.', file=sys.stderr)
        return 2
    try:
        with engine.connect() as connection:
            connection.execute(text('SELECT 1'))
    except SQLAlchemyError as error:
        print('PostgreSQL is unavailable (' + type(error).__name__ + '); no tests or database changes were run.', file=sys.stderr)
        return 2
    finally:
        engine.dispose()

    temporary = ROOT / 'artifacts' / ('pytest-api-' + uuid4().hex)
    environment = {**os.environ, 'MEETFLOW_TEST_DATABASE_URL': settings.database_url,
                   'GROQ_API_KEY': '', 'JIRA_API_TOKEN': '', 'HF_TOKEN': ''}
    result = subprocess.run([sys.executable, '-m', 'pytest', '-q', '-p', 'no:cacheprovider',
                             '--basetemp', str(temporary), '--tb=short'], cwd=ROOT, env=environment)
    return result.returncode


if __name__ == '__main__':
    raise SystemExit(main())

"""Local database maintenance. Never prints connection URLs or SQL exceptions."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from sqlalchemy import text
from app.database import engine
from app.migrations import migrate, migration_status


def backup():
    import shutil
    if engine.dialect.name != 'postgresql':
        raise RuntimeError('This backup command requires PostgreSQL.')
    binary = ROOT / '.runtime/postgres/pgsql/bin/pg_dump.exe'
    executable = str(binary) if binary.exists() else shutil.which('pg_dump')
    if not executable:
        raise RuntimeError('Install PostgreSQL client tools or add pg_dump to PATH.')
    url = engine.url
    folder = ROOT / 'data/backups'
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / ('meetflow-' + datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S-%f') + '.dump')
    env = {**os.environ, 'PGPASSWORD': url.password or ''}
    command = [executable, '-h', url.host or 'localhost', '-p', str(url.port or 5432),
               '-U', url.username or '', '-d', url.database, '-Fc', '-f', str(target)]
    result = subprocess.run(command, env=env, capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    if result.returncode:
        raise RuntimeError('Backup failed. Check PostgreSQL connectivity and client/server version compatibility.')
    print('Backup saved under data/backups/' + target.name + ' (ignored by Git).')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['migrate', 'status', 'check', 'backup'])
    action = parser.parse_args().action
    try:
        if action == 'migrate':
            done = migrate(engine)
            print('Applied: ' + ', '.join(done) if done else 'Database schema is current.')
        elif action == 'status':
            for item in migration_status(engine):
                print(item['version'] + ': ' + ('applied' if item['applied'] else 'pending'))
        elif action == 'backup':
            backup()
        else:
            with engine.connect() as connection:
                connection.execute(text('SELECT 1'))
            print('Database connection OK (' + engine.dialect.name + ').')
    except Exception as error:
        print('Database command failed (' + type(error).__name__ + '). Check connection, permissions and migration compatibility. Credentials and SQL withheld.', file=sys.stderr)
        return 1
    finally:
        engine.dispose()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

"""Project-local PostgreSQL lifecycle; no system service or global installation."""
import argparse
import json
import os
import secrets
import socket
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
BIN = ROOT / '.runtime' / 'postgres' / 'pgsql' / 'bin'
DATA = ROOT / 'data' / 'postgres'
CREDENTIALS = ROOT / '.runtime' / 'database.json'


def run(arguments, check=True):
    # PostgreSQL inherits handles from pg_ctl. A captured pipe can remain open
    # after pg_ctl exits, leaving the launcher stuck waiting for EOF.
    control_log = ROOT / '.runtime' / 'postgres-control.log'
    with control_log.open('w', encoding='utf-8') as output:
        try:
            return subprocess.run([str(argument) for argument in arguments], check=check,
                                  stdout=output, stderr=subprocess.STDOUT, text=True,
                                  creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
        except subprocess.CalledProcessError as error:
            error.stderr = control_log.read_text(encoding='utf-8', errors='replace')[-4000:]
            raise


def connection_url():
    credential = json.loads(CREDENTIALS.read_text())
    return 'postgresql+psycopg://minutes:'+quote(credential['password'], safe='')+'@127.0.0.1:55432/minutes'


def start():
    if not (BIN / 'pg_ctl.exe').exists() or not (DATA / 'PG_VERSION').exists():
        return False
    # Sandboxed callers may not inspect a database process started outside the
    # sandbox. Check the project's loopback port before trying to launch again.
    with socket.socket() as probe:
        probe.settimeout(2)
        if probe.connect_ex(('127.0.0.1',55432)) == 0:
            return True
    if run([BIN / 'pg_ctl.exe','status','-D',DATA],check=False).returncode != 0:
        run([BIN / 'pg_ctl.exe','start','-D',DATA,'-l',ROOT / 'data' / 'postgres.log','-w','-t','30'])
    return True


def initialize():
    import psycopg
    from psycopg import sql
    from dotenv import set_key
    if not (BIN / 'initdb.exe').exists():
        raise RuntimeError('PostgreSQL binaries are missing from .runtime/postgres/pgsql/bin.')
    if not CREDENTIALS.exists():
        CREDENTIALS.write_text(json.dumps({'password':secrets.token_urlsafe(30)}))
    credential = json.loads(CREDENTIALS.read_text())
    DATA.parent.mkdir(parents=True,exist_ok=True)
    if not (DATA / 'PG_VERSION').exists():
        password_file = ROOT / '.runtime' / 'init-password.txt'
        password_file.write_text(credential['password'],encoding='utf-8')
        try:
            run([BIN / 'initdb.exe','-D',DATA,'-U','minutes','--pwfile',password_file,'--auth','scram-sha-256','--encoding','UTF8','--locale','C'])
        finally:
            password_file.unlink(missing_ok=True)
        with (DATA / 'postgresql.conf').open('a') as configuration:
            configuration.write("\nlisten_addresses = '127.0.0.1'\nport = 55432\nshared_buffers = '64MB'\nmax_connections = 30\n")
    start()
    with psycopg.connect(host='127.0.0.1',port=55432,dbname='postgres',user='minutes',password=credential['password'],autocommit=True) as connection:
        if not connection.execute("SELECT 1 FROM pg_database WHERE datname = 'minutes'").fetchone():
            connection.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier('minutes')))
    migrate_archive()
    set_key(str(ROOT / '.env'),'DATABASE_URL',connection_url())
    set_key(str(ROOT / '.env'),'TRANSCRIPTION_PROVIDER','local')
    print('PostgreSQL initialized on localhost:55432. Existing meeting records were preserved.')


def migrate_archive():
    from sqlalchemy import create_engine, inspect, select
    from app.database import Meeting, Task
    from app.migrations import migrate
    target = create_engine(connection_url())
    migrate(target)
    source_path = ROOT / 'data' / 'meetings.db'
    if source_path.exists():
        source = create_engine('sqlite:///'+source_path.as_posix())
        with source.connect() as original, target.begin() as destination:
            for model in [Meeting, Task]:
                existing_columns = {column['name'] for column in inspect(source).get_columns(model.__tablename__)}
                selection = select(*[column for column in model.__table__.columns if column.name in existing_columns])
                for row in original.execute(selection).mappings():
                    if not destination.execute(select(model.id).where(model.id==row['id'])).first():
                        destination.execute(model.__table__.insert().values(**dict(row)))
        source.dispose()
    target.dispose()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action',choices=['initialize','start','stop'])
    args = parser.parse_args()
    try:
        if args.action == 'initialize': initialize()
        elif args.action == 'start': print('PostgreSQL ready.' if start() else 'Using externally configured database.')
        elif (DATA / 'PG_VERSION').exists(): run([BIN / 'pg_ctl.exe','stop','-D',DATA,'-m','fast','-w'])
    except subprocess.CalledProcessError as error:
        print(error.stderr or error.stdout, file=sys.stderr)
        sys.exit(1)

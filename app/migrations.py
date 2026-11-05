"""Ordered, transactional, forward-only migrations; no resets or down migrations."""
from pathlib import Path
from sqlalchemy import inspect, text

ROOT = Path(__file__).resolve().parent.parent
INITIAL = ROOT / 'migrations' / '001_initial.sql'
CONSTRAINTS = {
    'meetings': {
        'ck_meetings_status': "status IN ('queued','transcribing','analyzing','transcribed','ready','failed')",
        'ck_meetings_source': "source IN ('transcript','audio','sample')",
        'ck_meetings_title': 'length(trim(title)) > 0',
        'ck_meetings_duration': 'duration >= 0',
    },
    'tasks': {
        'ck_tasks_status': "status IN ('open','in_progress','done')",
        'ck_tasks_priority': "priority IN ('low','medium','high')",
        'ck_tasks_origin': "origin IN ('ai','manual')",
        'ck_tasks_jira_status': "jira_status IN ('not_sent','sending','sent','uncertain')",
        'ck_tasks_title': 'length(trim(title)) > 0',
    },
}


def initial(connection):
    for statement in INITIAL.read_text(encoding='utf-8').split(';'):
        if statement.strip():
            connection.execute(text(statement))


def integrity(connection):
    # Identifiers/types below are trusted migration constants, never request input.
    additions = {
        'meetings': {
            'audio_file': "VARCHAR(100) NOT NULL DEFAULT ''",
            'original_filename': "VARCHAR(250) NOT NULL DEFAULT ''",
            'description': "TEXT NOT NULL DEFAULT ''",
            'meeting_at': 'TIMESTAMP WITH TIME ZONE',
            'updated_at': 'TIMESTAMP WITH TIME ZONE',
            'transcript_created_at': 'TIMESTAMP WITH TIME ZONE',
            'analyzed_at': 'TIMESTAMP WITH TIME ZONE',
            'analysis_model': "VARCHAR(120) NOT NULL DEFAULT ''",
            'analysis_revision': 'INTEGER NOT NULL DEFAULT 0',
        },
        'tasks': {
            'origin': "VARCHAR(20) NOT NULL DEFAULT 'ai'",
            'created_at': 'TIMESTAMP WITH TIME ZONE',
            'updated_at': 'TIMESTAMP WITH TIME ZONE',
        },
    }
    for table, columns in additions.items():
        existing = {column['name'] for column in inspect(connection).get_columns(table)}
        for column, datatype in columns.items():
            if column not in existing:
                connection.execute(text(f'ALTER TABLE {table} ADD COLUMN {column} {datatype}'))
    connection.execute(text('UPDATE meetings SET updated_at = created_at WHERE updated_at IS NULL'))
    connection.execute(text("UPDATE meetings SET transcript_created_at = created_at WHERE transcript <> '' AND transcript_created_at IS NULL"))
    connection.execute(text('UPDATE tasks SET created_at = (SELECT created_at FROM meetings WHERE meetings.id = tasks.meeting_id) WHERE created_at IS NULL'))
    connection.execute(text('UPDATE tasks SET updated_at = created_at WHERE updated_at IS NULL'))
    if connection.dialect.name == 'postgresql':
        for column in ('segments', 'topics', 'decisions'):
            connection.execute(text(f'ALTER TABLE meetings ALTER COLUMN {column} TYPE JSONB USING {column}::jsonb'))
        for table, columns in [('meetings', ['updated_at']), ('tasks', ['created_at', 'updated_at'])]:
            for column in columns:
                connection.execute(text(f'ALTER TABLE {table} ALTER COLUMN {column} SET NOT NULL'))
                connection.execute(text(f'ALTER TABLE {table} ALTER COLUMN {column} SET DEFAULT CURRENT_TIMESTAMP'))
        for table, constraints in CONSTRAINTS.items():
            existing = {item['name'] for item in inspect(connection).get_check_constraints(table)}
            for name, condition in constraints.items():
                if name not in existing:
                    connection.execute(text(f'ALTER TABLE {table} ADD CONSTRAINT {name} CHECK ({condition})'))
    for name, table, columns in [
        ('ix_meetings_created_id', 'meetings', 'created_at, id'),
        ('ix_meetings_status', 'meetings', 'status'),
        ('ix_tasks_meeting_id', 'tasks', 'meeting_id'),
        ('ix_tasks_meeting_status', 'tasks', 'meeting_id, status'),
    ]:
        connection.execute(text(f'CREATE INDEX IF NOT EXISTS {name} ON {table} ({columns})'))


MIGRATIONS = [('001_initial', initial), ('002_integrity_metadata', integrity)]


def migrate(engine):
    with engine.begin() as connection:
        if connection.dialect.name == 'postgresql':
            connection.execute(text('SELECT pg_advisory_xact_lock(742019301)'))
        else:
            connection.exec_driver_sql('BEGIN IMMEDIATE')
        connection.execute(text('CREATE TABLE IF NOT EXISTS schema_migrations (version VARCHAR(80) PRIMARY KEY, applied_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT CURRENT_TIMESTAMP)'))
        applied = set(connection.execute(text('SELECT version FROM schema_migrations')).scalars())
        known = {version for version, _ in MIGRATIONS}
        if applied - known:
            raise RuntimeError('Database schema is newer than this application. Use the matching application version.')
        completed = []
        for version, upgrade in MIGRATIONS:
            if version not in applied:
                upgrade(connection)
                connection.execute(text('INSERT INTO schema_migrations (version) VALUES (:version)'), {'version': version})
                completed.append(version)
        return completed


def migration_status(engine):
    with engine.connect() as connection:
        applied = set(connection.execute(text('SELECT version FROM schema_migrations')).scalars()) if inspect(connection).has_table('schema_migrations') else set()
    return [{'version': version, 'applied': version in applied} for version, _ in MIGRATIONS]

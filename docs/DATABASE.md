# MeetFlow database setup and maintenance

## Repository audit and implementation decisions

The backend is Python 3.12, FastAPI, Uvicorn, SQLAlchemy 2, psycopg 3, and Pydantic. npm is a launcher/test wrapper, not a second backend. The frontend is HTML/CSS/JavaScript using same-origin `fetch`. `run.py` and `start.bat` start the existing server and project-local PostgreSQL. Playwright drives Chrome; pytest covers the backend. Dependencies remain unchanged by this integration.

Existing data already lived in PostgreSQL on this machine. Previously startup used `create_all` plus a few unversioned ALTER statements. The integration replaces that with transactional, numbered migrations, adds constraints/indexes/metadata, bounds the pool and API list queries, improves error handling, and verifies the actual workflow across restart. The UI design, AI model, prompts, and provider are preserved.

Input → `app/api.py` → PostgreSQL meeting row → `app/pipeline.py` → existing local Whisper or optional Groq transcription → saved transcript/segments → existing Groq analysis → atomic summary/decisions/topics/task update → existing frontend review and Jira/export routes.

**Schema choice:** this product has one current transcript and one current summary per meeting. Keeping their scalar fields on the meeting row preserves the existing identifiers, ORM and API without redundant one-to-one tables. Tasks are normalized child rows. JSONB holds ordered transcript segments and lists of topics/decisions because these are retrieved and edited as complete documents. Participants are derived from segment speaker labels; imported plain text has no independent participant directory. There are no user/team accounts. A local session protects access, but it is not user ownership or multi-tenant authorization.

## Current machine: start here

Python, dependencies, Whisper base, and PostgreSQL 17 are already installed under this project. The database listens only on `127.0.0.1:55432`; its name is `minutes`. Keep its existing secret DATABASE_URL.

```powershell
cd C:\Users\raghu\meeting-analysis
.\.venv\Scripts\python.exe scripts\manage_postgres.py start
npm run db:check
npm run db:backup
npm run db:status
npm run db:migrate
npm run dev
```

Open http://127.0.0.1:8000/app. `npm run dev` also starts the project-local database and applies pending migrations. An existing healthy MeetFlow server is recognized rather than launched twice. Stop that server with Ctrl+C in its original terminal before applying application updates; restarting is required to load changes to `.env`.

## Fresh Windows installation

Prerequisites: Python 3.12, Node/npm for convenience commands and browser tests, Chrome for browser tests, and PostgreSQL 17. Install PostgreSQL using the installer linked from the [official Windows download page](https://www.postgresql.org/download/windows/). Keep database connections local; do not open firewall ports for this college application.

Install the app dependencies:

```powershell
cd C:\Users\raghu\meeting-analysis
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-audio.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
npm ci
.\.venv\Scripts\python.exe scripts\prepare_model.py
```

Alternatively, `setup.ps1` installs Python dependencies and prepares the local audio model. Never overwrite an existing `.env` when installing.

Use SQL Shell (psql) or:

```powershell
& 'C:\Program Files\PostgreSQL\17\bin\psql.exe' -h 127.0.0.1 -U postgres -d postgres
```

In psql, create a dedicated local role/database (run once; no resets):

```sql
CREATE ROLE meetflow_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
\password meetflow_app
CREATE DATABASE meetflow OWNER meetflow_app;
\q
```

The password command prompts securely rather than putting the password into command history. Put a URL-encoded password in the ignored `.env`, using your own value:

```dotenv
DATABASE_URL=postgresql+psycopg://meetflow_app:YOUR_URL_ENCODED_PASSWORD@127.0.0.1:5432/meetflow
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=5
DB_POOL_TIMEOUT=10
DB_CONNECT_TIMEOUT=5
```

The Windows service manages this fresh PostgreSQL installation. The bundled `manage_postgres.py` commands apply only to `.runtime/postgres/pgsql` on the original machine. That original runtime was initialized with the `minutes` bootstrap role; it has elevated local cluster privileges. This integration does not change existing database ownership or roles. Use the limited role above for a fresh installation; moving an existing installation to a limited role should be a separately reviewed maintenance step.

Now run `npm run db:migrate`, `npm run db:check`, and `npm run dev`. `DATABASE_URL` selects storage; it does not copy data between arbitrary databases. The optional `manage_postgres.py initialize` command specifically imports the legacy local SQLite archive into the bundled PostgreSQL instance, preserving IDs and skipping already-present IDs.

### Optional Docker setup

The existing compose file is also supported. Set a strong `POSTGRES_PASSWORD` in `.env` first; there is no source-code fallback password. Run `docker compose up -d postgres`. This service creates database/user `minutes` on localhost:5432; configure DATABASE_URL to match those names and the URL-encoded password. Do not point at an unrelated existing volume or reset a volume to solve a password mismatch.

### Other environment settings

`GROQ_API_KEY` and the existing `GROQ_MODEL` drive analysis. `TRANSCRIPTION_PROVIDER=local` and `WHISPER_MODEL=base` preserve local transcription. Jira and optional Hugging Face variables remain as documented in `API_KEYS.md`. Real keys/passwords belong only in `.env`; `.env.example` contains blank fields/placeholders. Database URLs and passwords are never returned to the frontend.

## Tables and relationships

| Table | Purpose and important fields |
| --- | --- |
| `meetings` | Existing string UUID primary key; title, description, optional `meeting_at`, `created_at`, `updated_at`, source/status, duration, retained-audio filename; full TEXT transcript and summary; JSONB segments/topics/decisions; transcript creation timestamp; analyzed timestamp, model, revision; safe processing error. |
| `tasks` | Existing string UUID primary key; indexed FK `meeting_id`; ordered task title/description, owner, due phrase, priority/status, source quote, origin, Jira key/delivery state; created/updated timestamps. |
| `schema_migrations` | Applied migration version and timestamp. |

PostgreSQL timestamps use TIMESTAMPTZ. New metadata timestamps are maintained by SQLAlchemy for application writes. Historic task creation/update times are backfilled from the parent meeting because the old schema did not record them. Historic summary generation time/model remain unknown rather than being fabricated. `analysis_revision` counts successful generations after migration; it is **not** historical-summary storage. The product still keeps only its current summary.

Due dates retain their existing string format: AI may extract a phrase such as “before Friday”; it must not invent a calendar date. Task evidence is a verified source quote, not an invented segment foreign key. No independently identified transcript segments existed in the old model.

Checks validate meeting source/status, nonblank titles, nonnegative duration, task status/priority/origin/Jira state. The task FK prevents raw parent deletion with remaining children. The existing explicit meeting-delete API removes tasks transactionally via the ORM, then removes that meeting's audio file. It refuses active processing or active Jira delivery. It does not delete remote Jira issues. No automatic data-retention cleanup was added.

Indexes cover meeting chronological listing, meeting processing status, task meeting ownership, and meeting/status filtering. List queries use bounded pages and eager task loading. Large TEXT transcripts are omitted from list queries. Substring search still scans matching text and is intended for local college-project scale; full-text indexing is a future improvement if the archive becomes large.

## Migrations

| Version | Behavior |
| --- | --- |
| `001_initial` | Frozen baseline SQL in `migrations/001_initial.sql`. Creates missing tables without replacing existing tables. |
| `002_integrity_metadata` | Additive upgrade in `app/migrations.py`: timestamps/metadata, historical timestamp backfills, JSON-to-JSONB conversion, check constraints, indexes. No records, identifiers, or original content fields are removed. |

`npm run db:status` is read-only. `npm run db:migrate` applies pending migrations in one transaction under a PostgreSQL transaction advisory lock. Repeating it is a no-op. A failed validation/DDL statement rolls the upgrade and version entries back. Newer unknown migration versions are rejected. No downgrade/reset command is provided. Back up before upgrades and schedule them while processing is idle; table locks may briefly block other requests. Do not edit released migrations: add a new numbered upgrade.

SQLite remains supported for isolated browser/unit tests and a fresh installation without PostgreSQL. Foreign keys are enabled by the application's SQLite engine factory. Fresh SQLite tables get the baseline checks. Legacy SQLite tables receive additive columns but cannot receive all PostgreSQL ALTER constraints without a table rebuild; no destructive rebuild is performed. PostgreSQL is the verified primary target.

## Workflow, retries and concurrency

- Creation commits the meeting and imported transcript before scheduling processing. Uploaded recordings keep their existing retained-file workflow.
- An atomic queued-state claim prevents two processing workers from generating duplicate results for the same queued meeting.
- Transcription commits its full text, ordered segments, speakers/timestamps, and duration before AI analysis. A provider failure leaves these usable.
- Model inference and transcription run outside database transactions, returning connections to the pool.
- Summary, decisions, topics, generation metadata, and extracted tasks commit together. Failure rolls back the whole result update and retains the previous successful result.
- Regeneration reuses IDs for matching task titles, deduplicates repeated output titles, and preserves manual/reviewed tasks, task progress, and Jira links. Source evidence also prevents a reviewed renamed task from being duplicated when its exact quote matches. Semantically equivalent tasks with different titles and quotes cannot be reliably deduplicated automatically.
- Write routes acquire the meeting row before task rows. Active processing blocks related edits/deletion. Jira's existing claim/uncertain-delivery protection remains in place; a network timeout is not automatically resent.
- Restart recovery marks interrupted jobs as failed/retryable and interrupted Jira deliveries uncertain. This remains a single Uvicorn worker application, not a distributed job system.

Transcript import accepts up to 1,000,000 characters. Storage is PostgreSQL TEXT and never silently truncates content. The existing model workflow still analyzes at most 80,000 characters: larger transcripts are fully saved and displayed as “Transcript ready” with instructions to split them for analysis. Requests are bounded before parsing (4 MiB general bodies, 25 MiB multipart bodies); the existing recording limit remains 24 MiB. Chunking/model prompt changes are outside this integration.

## API reference

Open `/` or `/app` to obtain the existing HttpOnly session cookie. All API paths except health/liveness require it. Responses retain their existing shapes; cross-origin/private-host requests are 403, missing sessions 401, validation and malformed JSON are 422, missing records 404, processing/data conflicts 409, request limits 413/429, Jira upstream failures 502, unavailable database 503, and unexpected application errors use FastAPI's generic 500 response. This API has no endpoint that returns 400; FastAPI reports malformed/invalid request bodies as 422. The browser never connects directly to PostgreSQL.

| Method/path | Behavior |
| --- | --- |
| `GET /api/health/live` | Process liveness without a database query. |
| `GET /api/health` | Database readiness: `status`, `application`, `database`; returns 503 when the DB is unavailable. |
| `GET /api/settings` | Existing nonsecret provider/database readiness settings. |
| `POST /api/meetings` | Existing transcript creation, 202. Adds optional description and timezone-aware meeting_at. |
| `POST /api/upload` | Existing multipart audio/video creation, 202. |
| `GET /api/meetings?q=&limit=100&offset=0` | Existing array response; maximum 100 per page, stable chronological/ID order. The UI fetches successive pages and deduplicates IDs. |
| `GET /api/meetings/{id}` | Complete saved meeting, transcript, summary, segments, decisions and tasks. |
| `PATCH /api/meetings/{id}` | Update title, optional description, and optional timezone-aware meeting_at; null clears meeting_at. |
| `POST /api/meetings/{id}/retry` | Retry failed/transcribed meetings. Concurrent queued/active attempts return 409. |
| `POST /api/meetings/{id}/regenerate` | Reanalyze a ready meeting, 202. Exposed by the existing UI with confirmation. |
| `GET /api/tasks?meeting_id=&status=&owner=&limit=100&offset=0` | New bounded task list with optional exact filters. |
| `POST /api/meetings/{id}/tasks` | Existing manual task creation. |
| `PATCH /api/tasks/{id}` | Existing task editing/status; edited tasks are preserved as reviewed/manual. |
| `DELETE /api/tasks/{id}` | Existing task deletion; linked/uncertain Jira tasks remain protected. |
| `POST /api/tasks/{id}/jira` | Existing reviewed task delivery with duplicate-send protection. |
| `PATCH /api/meetings/{id}/speakers` | Existing speaker correction and corresponding owner updates. |
| `GET /api/meetings/{id}/audio`, `/export`, `/tasks.csv`, `/report` | Existing playback, Markdown, CSV and printable report. |
| `DELETE /api/meetings/{id}` | Existing explicit deletion semantics. |
| `POST /api/sample` | Existing clearly labeled curated example; PostgreSQL serializes concurrent sample creation. |

The UI still provides title editing; new description/date fields are currently API metadata. IDs are generated by the server. No client-supplied ownership field grants access. There are no user accounts, so independent authorized local sessions share the same single-user workspace; per-user cross-account authorization is not implemented or claimed. Public hosting would require authentication, ownership checks, a durable queue, and deployment work.

## Tests and actual verification

```powershell
$testTemp = Join-Path (Get-Location) ('artifacts/pytest-' + [guid]::NewGuid().ToString('N'))
.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider --basetemp $testTemp
npm run test:postgres
npm run test:api
npm run check
npm run test:landing
npm run test:browser
.\.venv\Scripts\python.exe scripts\check_secret_exposure.py
# Optional: real audio + one real Groq analysis request + process restart:
.\.venv\Scripts\python.exe scripts\verify_postgres_live.py
```

`npm run test:api` runs all pytest tests in one pass, including PostgreSQL tests using random `meetflow_test_<uuid>` schemas. It checks PostgreSQL connectivity first and exits before running tests if unavailable. The configured user needs permission to create/drop these generated test schemas; public/development tables are never dropped or truncated. Real Groq/HF/Jira credentials are disabled in the test process, and provider calls use mocks. `npm run test:postgres` runs only the PostgreSQL suite; ordinary pytest skips those opt-in tests unless `MEETFLOW_TEST_DATABASE_URL` is set. The route inventory test fails when an API method is added without updating coverage. `verify_postgres_live.py` is a separate optional test using real local Whisper and Groq on a synthetic spoken test fixture, restarts an isolated server on port 8131, tests playback/exports, and removes its own test meeting/schema. It never sends Jira issues.

The API suite checks every registered API method and route, successful response contracts, private-session access, malformed requests, invalid IDs/filters, SQL-injection search strings, provider errors and timeouts, PostgreSQL migrations, constraints, rollback, CRUD, concurrency, startup and database failures. Run `npm run test:api` for current totals; this document does not assume tests pass without execution. Browser regression suites remain separate commands: `npm run test:browser` and `npm run test:landing`.

One existing Starlette test-client deprecation warning remains. Automatic diarization still requires its optional model access; actual Jira issue creation was not performed as part of these tests. Backup creation was verified; a full restore was not executed against user data.

## Backup and restore

`npm run db:backup` calls pg_dump in custom format and saves a timestamped file under ignored `data/backups`. Passwords are passed only through the child environment, not command arguments. Back up `data/uploads` as well: recordings are files, not database blobs. Take filesystem backups while recording uploads/deletes are idle.

For restore, use a **new empty database** and keep the original untouched:

```powershell
& 'C:\Program Files\PostgreSQL\17\bin\createdb.exe' -h 127.0.0.1 -U postgres -O meetflow_app meetflow_restored
& 'C:\Program Files\PostgreSQL\17\bin\pg_restore.exe' -h 127.0.0.1 -U meetflow_app -d meetflow_restored --no-owner --no-privileges --exit-on-error 'C:\path\to\backup.dump'
```

Use password prompts. For the bundled runtime use its `.runtime/postgres/pgsql/bin` tools, port 55432 and the configured local role. Verify the restored database before choosing to change DATABASE_URL. Do not use `--clean`, drop an existing database, or overwrite recordings without a reviewed recovery plan. See [official pg_dump documentation](https://www.postgresql.org/docs/17/app-pgdump.html).

## Troubleshooting and limits

- **Connection refused:** start PostgreSQL; distinguish bundled port 55432 from a system installation's 5432. Run `npm run db:check`.
- **Wrong password:** update the ignored `.env` with the correct URL-encoded password; changing `.env` does not change the PostgreSQL role's actual password. Restart MeetFlow afterward.
- **Port 8000 occupied:** an existing healthy MeetFlow instance is reused. Stop its original terminal with Ctrl+C to load new code. The launcher does not kill unrelated programs.
- **Migration fails:** inspect status; verify role privileges, PostgreSQL version and existing constraint values. The transaction rolls back. Logs intentionally show exception type, not SQL/parameters. Investigate locally with a trusted database client; never paste credentials or full sensitive rows into issues. Do not reset the database.
- **Temporary-folder permission errors in pytest:** use the unique project-local `--basetemp` command above. This avoids older sandbox-owned Windows temp folders.
- **Provider failure:** transcript and prior analysis remain saved. Correct connectivity/configuration and retry; account rate limits still apply.
- **Pool exhaustion:** default maximum is 10 connections per app process with a 10-second checkout timeout, 5-second connect timeout, 30-second statement timeout and 10-second lock timeout. Use one app worker. Slow Whisper/Groq work does not reserve pool connections.
- **Database outage during background processing:** error logging records the class only. If even the failure state cannot be saved, restarting after recovery marks the interrupted job retryable. There is no durable external job queue or exactly-once cross-service transaction.
- **Scale:** list endpoints are bounded, but the current frontend aggregates the local archive over pages for its dashboard. Concurrent archive changes can shift offset pages; refresh resolves this. Cursor pagination and server-side aggregate dashboards are future work for large/multi-user archives.

Connection-pool choices follow the [SQLAlchemy pooling documentation](https://docs.sqlalchemy.org/en/20/core/pooling.html). Row/advisory locking follows [PostgreSQL locking documentation](https://www.postgresql.org/docs/17/explicit-locking.html).

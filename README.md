# AI-Powered Meeting Analysis & Task Automation System

**MeetFlow** is a working college project built from the supplied presentation. It captures meeting recordings, transcribes speech, extracts summaries and commitments, and turns reviewed action items into Jira issues.

## Open the website

From PowerShell or the VS Code terminal on this Windows machine:

```powershell
cd C:\Users\raghu\meeting-analysis
npm run dev
```

This starts the local database and the website. Keep the terminal open, then visit **http://127.0.0.1:8000** for the landing page or **http://127.0.0.1:8000/app** for the workspace. Press **Ctrl+C** to stop the website. `npm start` runs the same launcher. You can also double-click `start.bat` in this folder without opening a terminal first.

To open the codebase in VS Code, run `code C:\Users\raghu\meeting-analysis`, or use **File → Open Folder** and select that folder. These launch commands use the existing `.venv` and `.env`; no API keys belong in the command.

If MeetFlow is already running, the launcher prints its URLs and exits successfully without starting a duplicate server. If a different program occupies port 8000, it reports the conflict without stopping that program. Stop the existing website with Ctrl+C in its original terminal when you need to restart it after configuration changes.

On this machine, double-click **start.bat** and open **http://127.0.0.1:8000**. Python, the full audio dependencies, the local Whisper base model, and a project-local PostgreSQL database are already installed. The launcher starts the database automatically. Existing meeting history has been preserved.

Use **New meeting** to upload audio, record your microphone, or paste a transcript. **Explore a sample** opens a clearly labeled example with summaries, decisions, speakers, and tasks. Real recordings already transcribe without an API key. Without a Groq key, the transcript remains available and the meeting displays **Transcript ready**. Configure the key later and click **Run AI analysis**.

Credentials belong in the backend `.env`. See [API_KEYS.md](API_KEYS.md) for exact links and values. There is no service settings form in the website.

## What works

The homepage at `/` introduces MeetFlow with an interactive illustrative preview, a conversation-to-plan comparison, and FAQs. `/app` opens the working workspace. The homepage's upload and sample links open the corresponding workflow directly. Run `npm run test:landing` to check the landing page interactions, mobile layouts, and app handoff.

- Audio/video uploads: MP3, WAV, M4A, MP4, WebM, OGG, FLAC; up to 24 MB.
- Browser microphone recording with timer, playback preview, and submission.
- Local faster-Whisper transcription with timestamps and retained audio playback; click a timestamp to seek.
- Optional pyannote community-1 speaker detection and editable speaker names.
- Groq analysis into a summary, topics, decisions, and action items with source quotes.
- Task creation, editing, deletion, owners, due phrases, priorities, and To do / In progress / Done states.
- Task list and board views, decision log, and searchable meeting archive.
- Single or bulk Jira issue creation after review, linked issue URLs, and duplicate-send protection.
- Markdown notes, CSV action items, and a printable report that can be saved as PDF using Ctrl+P.
- PostgreSQL persistence, responsive desktop/mobile layouts, and clear retry states.

Local transcription and database storage need no API keys. Live AI analysis, gated speaker models, and Jira calls require the credentials described in the guide. Sample notes are curated content, not live AI output.

## Architecture

All screens share `static/theme.css` for the cream, sage, and terracotta palette and typography. `landing.css` handles the homepage, `workspace.css` handles every workspace screen and dialog, and `report.css` applies the same visual language to printable reports.

`workspace-layout.css` adapts the landing page's horizontal navigation, centered content, editorial headings, and capture card to the working application, including mobile layouts. The capture card opens the existing upload, microphone, and transcript workflows.

```mermaid
flowchart LR
  Browser[HTML / CSS / JavaScript] --> API[FastAPI / Uvicorn]
  API --> DB[(PostgreSQL)]
  API --> Whisper[faster-Whisper]
  Whisper --> Speakers[Optional pyannote.audio]
  Speakers --> Groq[Groq analysis model]
  Groq --> Review[Summary / Decisions / Tasks]
  Review --> DB
  Review --> Jira[Jira REST API v3]
```

| File                         | Purpose                                                                                 |
| ---------------------------- | --------------------------------------------------------------------------------------- |
| `app/main.py`                | Application composition, middleware, routers and static website                         |
| `app/api.py`                 | Uploads, meeting search, analysis retry, Jira delivery and exports                       |
| `app/pipeline.py`            | Recording-to-transcript-to-analysis processing and saved task extraction                 |
| `app/lifecycle.py`           | Database initialization and recovery of interrupted jobs                                |
| `app/serialization.py`       | Public response formatting and secret redaction                                         |
| `app/workspace.py`           | Meeting review, speaker correction, tasks, playback, reports                            |
| `app/services.py`            | Transcription, diarization, Groq and Jira adapters                                      |
| `app/database.py`            | Meeting and task models                                                                 |
| `app/schemas.py`             | Input and AI response validation                                                        |
| `static/workspace.js`        | Browser routing, capture, review and task interactions                                  |
| `static/workspace.css`       | Responsive interface                                                                    |
| `scripts/manage_postgres.py` | Project-local PostgreSQL lifecycle and initial archive migration                        |
| `scripts/prepare_model.py`   | Official Whisper checkpoint download, checksum verification and CTranslate2 preparation |

API documentation and OpenAPI schema routes are disabled. The API accepts a private browser session issued when the local website opens. [PROJECT_NOTES.md](PROJECT_NOTES.md) contains the college demonstration flow and database design.

Audio is retained under `data/uploads` until its meeting is deleted. Transcripts and analysis live in the database. AI source quotations are checked against the original transcript. Manually added tasks survive AI processing. Speaker correction also updates matching task owners that have not been sent to Jira.

Jira issue creation uses a database claim so repeated clicks cannot create the same issue twice. Interrupted requests are marked `uncertain`; automatic resending is blocked. Check Jira for the label `minutes-<task UUID>` when reconciling an uncertain request. Owner names and due phrases appear in the issue description. Local task progress does not change the Jira workflow status.

## Install on another computer

Use Python 3.12. Run `setup.ps1` on Windows, or perform the equivalent steps:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-audio.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe scripts\prepare_model.py
.\start.bat
```

The model preparation script downloads the official Whisper base checkpoint and tokenizer, verifies the checkpoint hash, and converts it for faster-Whisper. Downloads require internet access; subsequent transcription is local. Standard faster-Whisper Hub downloads also work when a different `WHISPER_MODEL` is selected and the Hub is reachable. Audio decoding uses PyAV's bundled libraries, so a separate system FFmpeg installation is not required for the implemented pipeline.

For PostgreSQL on another machine, use an existing PostgreSQL installation or the supplied Docker Compose file:

```powershell
docker compose up -d postgres
```

Then set `DATABASE_URL=postgresql+psycopg://minutes:minutes@localhost:5432/minutes` in `.env` and restart. Update the password in both places if changed. Fresh installations can use the SQLite default while preparing PostgreSQL. Switching arbitrary connection strings does not migrate data; the project-local initialization script specifically migrates the existing SQLite archive.

The Windows runtime downloaded for this machine is under `.runtime/postgres/pgsql`. If copying that runtime to another Windows machine, use `scripts/manage_postgres.py initialize` to initialize a new database and generate its credentials. Do not copy a running database folder.

`requirements-lock.txt` records core packages; `requirements-audio-lock.txt` records the tested full Windows environment. Portable requirements allow each platform to choose matching binary wheels. JavaScript dependencies are only used for developer checks; the website needs no frontend build step.

## Verify

```powershell
.\.venv\Scripts\python.exe -m pytest -q
npm install
npm run check
npm run test:browser
```

The browser test starts an isolated database/server, uses Chrome and a spoken WAV fixture, and exercises upload/transcription/playback, imports, fake microphone capture, task CRUD/persistence, speaker correction, search, board, exports, reports, and mobile overflow checks. Set `CHROME_PATH` if Chrome is elsewhere. Screenshots go to `artifacts/`.

Verified on this machine: **24 automated backend tests**, the complete browser flow, actual local speech transcription, and live Groq analysis with a synthetic transcript. Jira contracts use mocked HTTP responses; Jira delivery and gated pyannote inference are awaiting their credentials.

## Privacy and request limits

The Groq credential is in the ignored backend `.env`, never in frontend code or browser requests. Credential fields are excluded from settings serialization and object representations. Known secrets and Groq-key patterns are redacted from records, exports, validation errors and logs. HTTP access logging is disabled so search URLs are not logged. `scripts/protect_secrets.ps1` protects the environment file's Windows permissions.

The website binds only to `127.0.0.1`. Requests from remote clients or untrusted hosts are rejected. API access requires an opaque 12-hour HttpOnly, SameSite=Strict session cookie. This cookie contains no provider credentials. Cross-site reads and writes are rejected. Private responses use `Cache-Control: no-store`. Opening or refreshing the local website establishes a new session after a server restart.

Limits apply per local client address and cannot be bypassed with forwarding headers:

| Operation                                            | Limit                              |
| ---------------------------------------------------- | ---------------------------------- |
| All API requests                                     | 120 per minute                     |
| Writes                                               | 30 per minute                      |
| Uploads, transcript submissions and analysis retries | 3 per minute, 20 per hour          |
| Actual outbound Groq requests                        | 3 per minute, 20 per hour globally |

Rejected requests return HTTP 429 with `Retry-After`. Groq's own HTTP 429 responses start a shared cooldown. Limits are configurable through `.env.example` and are counted atomically in the single server process. Counters reset on restart; these are usage safeguards, not a persistent billing cap. Groq account quotas and spending limits still apply.

The former Llama 3.3 model was absent from the account's available model list. The backend now uses the verified `qwen/qwen3.8-27b` model with JSON validation. Keep the model configurable as provider availability changes.

## Scope

This is a single-user local college application. The launcher binds to `127.0.0.1`. Recording captures the microphone and processes after submission; it is not streaming transcription or a Zoom/Meet bot. Transcript limit is 80,000 characters. Processing runs in one server process; use one Uvicorn worker. Interrupted jobs can be retried using their retained transcript or recording.

Before public hosting, add authentication, per-user permissions, a durable job queue, and deployment configuration. `.env`, recordings, databases and local runtimes are excluded from source control.

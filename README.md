# Memory

Memory connects Google Drive and selected local folders, indexes files semantically, and helps users search and explore related documents through a polished spatial interface.

For a repo-friendly walkthrough of the architecture, tech stack, data flow, and current boundaries,
see [docs/ARCHITECTURE_TOUR.md](docs/ARCHITECTURE_TOUR.md).

This repository now includes the Milestone 5 product shell: authenticated entry, real source
connection controls, synchronization status, search-first home, spatial/timeline/list result
exploration, file inspection, grounded Ask Memory session UI, settings/privacy controls, and
responsive error recovery around the existing backend and desktop contracts.

## Requirements

- Node.js 22+
- pnpm 11+
- Python 3.12+
- Docker Desktop or compatible Docker engine

## Setup

```bash
pnpm install
python3 -m venv .venv
.venv/bin/pip install -e 'apps/api[dev]'
cp .env.example apps/api/.env
docker compose -f infrastructure/docker-compose.yml up -d
cd apps/api && ../../.venv/bin/alembic upgrade head
```

Set `GEMINI_API_KEY` in `apps/api/.env` before running real ingestion or search.
Set `MEMORY_AUTH_TOKEN_SECRET` to a random secret before using protected APIs with real data.

For Google Drive, create an OAuth client in Google Cloud Console and set:

```bash
GOOGLE_OAUTH_CLIENT_ID=...
GOOGLE_OAUTH_CLIENT_SECRET=...
GOOGLE_OAUTH_REDIRECT_URL=http://127.0.0.1:8000/sources/google-drive/oauth/callback
GOOGLE_OAUTH_FRONTEND_RETURN_URL=http://127.0.0.1:5173
OAUTH_CREDENTIAL_ENCRYPTION_KEY=...
```

Generate a local encryption key with:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

In Google Cloud Console, add the redirect URL above to the OAuth client. The app requests
`drive.readonly`, `openid`, `email`, and `profile`. Until the OAuth consent screen is verified or
published for broader use, add your Google account as a test user.

## Run Locally

All-in-one runner:

```bash
pnpm dev
```

This starts Docker services, applies migrations, and launches the API and web app.

Manual commands:

```bash
pnpm --filter @memory/web dev
.venv/bin/uvicorn app.main:app --app-dir apps/api --reload
```

Desktop shell:

```bash
pnpm --filter @memory/desktop dev
```

## Product Experience

The web and desktop shells render the shared `@memory/ui` experience. Returning signed-in users land
directly in the product; first-run users see a short onboarding flow that explains source consent,
indexing, uploaded extracted content, and removal controls.

Search uses `POST /search` with the real shared contract from `@memory/types`. The frontend does not
calculate semantic similarity. Results can be explored through:

- Space: a React Three Fiber / Three.js relationship map with stable deterministic coordinates and
  an SVG/list fallback for reduced motion or unavailable WebGL.
- Timeline: locale-aware date buckets from indexed metadata.
- List: keyboard-navigable conventional rows with source, path, excerpt, match reason, and actions.

Ask Memory is scoped to the selected file, nearby cluster, or current result set and only answers
from visible indexed evidence. Until a backend grounded-answer endpoint is added, it clearly uses
the current cited search evidence and reports insufficient evidence instead of manufacturing
citations.

## Google Drive Sync

1. Start the API and web app.
2. Sign in with an email address in the UI. The backend returns a signed bearer token; source and
   search requests use that token as the authoritative user identity.
3. Click **Connect Google Drive** and complete Google OAuth.
4. Run **Sync now**. Initial sync discovers supported files, exports Google-native documents,
   downloads supported uploads, hashes content, and sends changed bytes through extraction, chunking,
   embedding, and indexing.
5. Search for a natural-language phrase and open a Drive result from the search list.
6. Run sync again. Unchanged content is skipped; Drive changes update added, modified, renamed,
   moved, trashed, deleted, and restored files.

Supported initial Drive content: Google Docs, Slides, Sheets, Drawings when export is available,
PDF, DOCX, PPTX, plain text, Markdown, common source-code files, CSV, and metadata-only records for
recognized image or 3D asset MIME families. Unsupported files are recorded as failed/skipped
document states instead of silently disappearing.

Known limitation: this repository does not yet include a durable worker queue, so Drive sync runs
inside the API request while persisting progress and summaries. The next milestone should move these
jobs to a queue with persisted retry scheduling.

## Local Folder Sync

The desktop app supports native folder selection, approved-root scanning, file watching, open/reveal
actions, durable pending changes, restart-safe watcher restoration, and metadata-only records for
supported image/3D asset families. See [docs/LOCAL_FOLDERS.md](/Users/stephenlee/Software%20Projects/Memory/docs/LOCAL_FOLDERS.md)
for the desktop architecture, Tauri capability notes, ignore rules, watcher behavior, identity
strategy, offline queue behavior, platform limitations, and manual verification checklist.

## Ingest And Search Fixtures

After Docker is running and migrations have been applied:

```bash
.venv/bin/memory-api ingest-fixtures apps/api/tests/fixtures/ingest
.venv/bin/memory-api search "how does Memory protect OAuth tokens?"
```

The CLI uses real Gemini embeddings through the backend process. The API key stays in
`apps/api/.env` or the shell environment and is never sent to the frontend.

## Checks

```bash
pnpm test
pnpm format:check
pnpm lint
pnpm typecheck
.venv/bin/ruff check apps/api
.venv/bin/mypy --config-file apps/api/pyproject.toml apps/api/app
.venv/bin/pytest apps/api
MEMORY_INTEGRATION_DATABASE_URL=postgresql+asyncpg://memory:memory@localhost:5432/memory .venv/bin/pytest apps/api/tests/test_integration_ingestion_search_pg.py
```

## Before Production

Track production cutover work in [docs/PRODUCTION_READINESS.md](/Users/stephenlee/Software%20Projects/Memory/docs/PRODUCTION_READINESS.md).
The current development sign-in must be connected to a real identity provider before release.

## Manual Real-Account Verification

Use a non-sensitive Google account or test folder. Do not paste tokens or personal file contents into
fixtures, logs, or documentation.

- Connect a real Google account and confirm the requested scopes.
- Sync at least one Google Doc, one Google Slides file, one PDF, and one source-code or text file.
- Search for a phrase that exists semantically in a file but not exactly in the filename.
- Confirm relevant Drive files appear and open in Google Drive.
- Modify one Drive file, run incremental sync, and confirm only changed content is reprocessed.
- Rename one file and confirm metadata updates without a new embedding when the hash is unchanged.
- Trash a file and confirm it disappears from active search results.
- Disconnect Drive and confirm the source state is `disconnected` and local credentials are removed.

## Local Services

- PostgreSQL: `localhost:5432`
- Redis: `localhost:6379`
- MinIO API: `http://localhost:9000`
- MinIO console: `http://localhost:9001`

Default local credentials are development-only and listed in [.env.example](/Users/stephenlee/Software%20Projects/Memory/.env.example).

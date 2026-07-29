# Architecture Tour

Memory is a private semantic search application for files in Google Drive and user-selected local
folders. It combines a React product shell, a Tauri desktop bridge, a FastAPI backend, PostgreSQL
with pgvector, local object storage, and a real ingestion and retrieval pipeline.

This page is the high-level walkthrough for people exploring the repository. Deeper references live
in [ARCHITECTURE.md](ARCHITECTURE.md), [DATA_MODEL.md](DATA_MODEL.md),
[API_CONTRACTS.md](API_CONTRACTS.md), and [LOCAL_FOLDERS.md](LOCAL_FOLDERS.md).

## Repository Map

```text
apps/
  api/       FastAPI service, database models, migrations, source connectors, ingestion, search
  web/       Vite React web shell that renders the shared Memory experience
  desktop/   Tauri 2 desktop shell for native local-folder capabilities
packages/
  ui/        Shared React UI, design tokens, search experience, spatial graph view
  types/     Shared TypeScript contracts used by the frontend
infrastructure/
  docker-compose.yml  Local PostgreSQL, Redis, and MinIO
docs/        Product, architecture, API, data model, security, and readiness notes
scripts/     Local development runner
```

## Tech Stack

| Layer                 | Technology                                            | What it does                                                                                                        |
| --------------------- | ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| Web app               | React 19, Vite, TypeScript                            | Runs the browser product experience.                                                                                |
| Desktop app           | Tauri 2, Rust, React                                  | Adds native folder picking, safe scanning, file watching, open/reveal actions, and offline pending changes.         |
| Shared UI             | `@memory/ui`, React Three Fiber, Three.js             | Provides the reusable Memory interface, including list, timeline, and spatial result views.                         |
| Shared contracts      | `@memory/types`                                       | Keeps frontend request and response shapes aligned with API contracts.                                              |
| Backend API           | FastAPI, Pydantic Settings, SQLAlchemy async          | Owns auth, source management, ingestion, search, health, and readiness routes.                                      |
| Database              | PostgreSQL, pgvector, Alembic                         | Stores users, sources, documents, chunks, ingestion jobs, relationships, graph positions, metadata, and embeddings. |
| Cache and future jobs | Redis                                                 | Used for readiness now and reserved for job coordination, rate limits, and short-lived state.                       |
| Object storage        | MinIO with S3-compatible APIs                         | Local development storage for original and extracted artifacts.                                                     |
| Embeddings            | Google Gemini embeddings                              | Embeds indexed chunks and backend search queries.                                                                   |
| Extraction            | `pypdf`, `python-docx`, `python-pptx`, text parsers   | Extracts indexable text from supported document families.                                                           |
| Tooling               | pnpm workspaces, ESLint, Prettier, Ruff, mypy, pytest | Keeps the monorepo typed, linted, formatted, and testable.                                                          |

## System Shape

```mermaid
flowchart LR
  User["User"] --> Web["apps/web<br/>React + Vite"]
  User --> Desktop["apps/desktop<br/>Tauri + React"]
  Web --> UI["packages/ui<br/>Shared product shell"]
  Desktop --> UI
  Desktop --> Native["Rust commands<br/>folder picker, watcher, open/reveal"]
  UI --> API["apps/api<br/>FastAPI"]
  API --> PG["PostgreSQL + pgvector"]
  API --> Redis["Redis"]
  API --> S3["MinIO / S3"]
  API --> Gemini["Gemini embeddings"]
  API --> Drive["Google Drive API"]
```

The web and desktop apps intentionally share the same React experience. The desktop shell adds a
small native boundary for local folders, while the backend remains the authority for identity,
source ownership, ingestion state, and search.

## Main User Flow

1. A user signs in through `POST /auth/sign-in`.
2. The API returns a signed bearer token, and protected routes use that token as the authoritative
   user identity.
3. The user connects a source:
   - Google Drive uses a server-side OAuth authorization-code flow with PKCE.
   - Local folders are approved through the Tauri desktop shell.
4. Source files are discovered, hashed, extracted, chunked, embedded, and written to PostgreSQL.
5. Search queries are embedded on the backend and matched against user-scoped chunks.
6. Results return excerpts, source metadata, scoring signals, and UI-ready document records.
7. The shared UI renders results as a spatial graph, timeline, or keyboard-navigable list.

## Authentication And Isolation

Memory treats file paths, extracted text, embeddings, OAuth credentials, and answer traces as
sensitive data.

- The API signs bearer tokens with `MEMORY_AUTH_TOKEN_SECRET`.
- User-owned tables include `user_id`.
- Source, document, chunk, ingestion, and search routes scope reads and writes to the authenticated
  user.
- Google refresh-token payloads are encrypted before storage.
- Google access tokens are short-lived, refreshed server-side, and never returned to the frontend.
- Local folder search results expose relative paths instead of absolute paths.
- Development mocks must be enabled explicitly with `MEMORY_ENABLE_DEVELOPMENT_MOCKS=true`.

## Source Connectors

### Google Drive

Google Drive sync lives in `apps/api/app/google_drive`.

The backend requests `drive.readonly`, `openid`, `email`, and `profile`. It stores non-secret account
and sync metadata on the source row and stores encrypted refresh credentials separately. Initial sync
lists supported files, exports Google-native formats when possible, downloads supported uploaded
files, hashes bytes, and ingests only changed content. Incremental sync uses the Drive changes cursor
to handle content changes, renames, moves, trash events, deletion, and restoration.

The current implementation runs Drive sync inside API requests while persisting status, summaries,
and failures. A durable worker queue is the next architectural step.

### Local Folders

Local folder access belongs to the Tauri desktop app in `apps/desktop/src-tauri`.

Rust commands own folder selection, canonical path validation, scanning, watching, and open/reveal
actions. The backend never scans arbitrary local paths. Instead, the desktop uploads files from
approved roots through typed local-folder API routes. The desktop keeps a durable pending-change
queue with metadata only, so file contents are read at upload time and are not stored in the queue.

Local identity prefers platform file IDs when available, which lets renames and moves update
metadata without unnecessary re-embedding. Content hashes are still the final source of truth for
whether extraction and embeddings need to run.

## Ingestion Pipeline

```mermaid
sequenceDiagram
  participant Source as Source connector
  participant API as FastAPI
  participant DB as PostgreSQL
  participant Extract as Extract/normalize/chunk
  participant Gemini as Gemini embeddings

  Source->>API: file metadata + content bytes
  API->>DB: upsert source/document state
  API->>API: SHA-256 content hash
  alt content unchanged
    API->>DB: record skipped ingestion job
  else content changed
    API->>Extract: extract text and normalize blocks
    Extract->>Extract: deterministic chunking
    Extract->>Gemini: embed chunks + document representation
    Gemini-->>API: vectors
    API->>DB: replace chunks, vectors, metadata, status
  end
```

The ingestion code lives in `apps/api/app/ingestion`. It supports text, Markdown, PDF, DOCX, PPTX,
CSV, and common source-code files. Image, 3D, and CAD-like families are tracked as metadata-only
records when extraction is not appropriate.

Each ingestion attempt creates an `ingestion_jobs` row. If a file's indexed content hash already
matches the new hash, the job is marked `skipped` and embeddings are not regenerated.

## Search And Retrieval

Search lives in `apps/api/app/search`.

The backend embeds the query using the configured Gemini embedding model, performs pgvector
nearest-neighbor search over `document_chunks`, blends semantic similarity with PostgreSQL text rank,
and returns document-level results. The scoring weights are currently:

- Semantic chunk similarity: `0.82`
- Text match rank: `0.18`

Search excludes deleted documents and filters by `user_id`, so one user's chunks cannot appear in
another user's results. The response includes excerpts and machine-readable explanations so the UI
can show why a result matched.

## Frontend Experience

The main product experience is `MemoryFoundation` in `packages/ui`.

It handles:

- First-run onboarding.
- Email sign-in and token storage.
- Google Drive connection and sync status.
- Desktop local-folder controls when running inside Tauri.
- Natural-language search.
- Result filtering, sorting, selection, and search history.
- Space, timeline, and list result views.
- An Ask Memory interface scoped to visible evidence.

The spatial result view uses React Three Fiber and Three.js when available, with a non-WebGL fallback
for reduced motion or unsupported environments. The frontend does not compute semantic similarity;
it relies on backend search contracts.

## Data Model

The core tables are:

- `users`: account identity and profile metadata.
- `sources`: Google Drive accounts and local folder roots, including sync cursors and source status.
- `documents`: provider file identity, title, MIME type, hashes, metadata, status, object keys,
  document embedding, and graph coordinates.
- `document_chunks`: normalized text chunks, chunk metadata, token counts, hashes, and chunk
  embeddings.
- `ingestion_jobs`: retry-safe ingestion history with failure codes and messages.
- `document_relationships`: planned weighted edges for semantic, shared-source, explicit-reference,
  and temporal-neighbor relationships.

Alembic migrations in `apps/api/alembic/versions` define the schema and pgvector columns.

## Local Development Runtime

`pnpm dev` runs `scripts/run-app.sh`, which starts local services, applies migrations, launches the
FastAPI service, and runs the web app.

Manual development pieces:

```bash
docker compose -f infrastructure/docker-compose.yml up -d
cd apps/api && ../../.venv/bin/alembic upgrade head
.venv/bin/uvicorn app.main:app --app-dir apps/api --reload
pnpm --filter @memory/web dev
pnpm --filter @memory/desktop dev
```

Local services:

- PostgreSQL: `localhost:5432`
- Redis: `localhost:6379`
- MinIO API: `http://localhost:9000`
- MinIO console: `http://localhost:9001`

## Current Boundaries

Implemented in this repository:

- Shared React web and desktop product shell.
- Backend auth token flow.
- Health and readiness checks.
- Google Drive OAuth, status, sync, disconnect, failure inspection, retry, and open routes.
- Tauri local-folder selection, scanning, watching, open/reveal support, and backend contracts.
- Real extraction, chunking, Gemini embedding, indexing, and semantic search.
- PostgreSQL data model, pgvector storage, and API tests.

Still intentionally future work:

- Durable background worker queue for sync and ingestion jobs.
- Production identity-provider integration.
- Backend grounded-answer endpoint with citations.
- Relationship generation jobs and full graph API.
- Production object-storage and secret-management hardening.

## Quality Gates

Use these checks before treating architecture changes as complete:

```bash
pnpm check
pnpm test
.venv/bin/ruff check apps/api
.venv/bin/mypy --config-file apps/api/pyproject.toml apps/api/app
.venv/bin/pytest apps/api
```

For real retrieval behavior, run PostgreSQL and then execute the integration search test:

```bash
MEMORY_INTEGRATION_DATABASE_URL=postgresql+asyncpg://memory:memory@localhost:5432/memory .venv/bin/pytest apps/api/tests/test_integration_ingestion_search_pg.py
```

# Architecture

## System Shape

- `apps/web`: React TypeScript web interface.
- `apps/desktop`: Tauri 2 shell that reuses the shared React interface and will provide native local-folder capabilities.
- `apps/api`: FastAPI backend.
- `packages/ui`: design tokens and shared interface primitives.
- `packages/types`: TypeScript contracts.
- `infrastructure`: local PostgreSQL, Redis, and MinIO services.

## Storage

- PostgreSQL stores users, sources, documents, chunks, relationships, graph coordinates, metadata, and pgvector embeddings.
- Redis is reserved for job coordination, rate-limit state, and short-lived readiness/cache data.
- MinIO provides S3-compatible local object storage for originals and extracted text.

## Future Sync Pipeline

1. Source connector discovers changed files.
2. Sync state records provider cursors or local folder snapshots.
3. Objects are stored under user-scoped S3 keys.
4. Text extraction creates normalized text artifacts.
5. Chunker writes document chunks.
6. Embedding jobs write chunk-level and document-level vectors.
7. Relationship jobs create weighted edges.
8. Graph coordinate jobs update stable positions only when necessary.

## Google Drive Synchronization

Google Drive uses a server-side OAuth authorization-code flow with PKCE. The backend stores only an
encrypted refresh token payload on the `sources` row for the authenticated application user. Access
tokens are short-lived, refreshed server-side, and are not returned to the frontend.

The Drive connector requests `drive.readonly`, `openid`, `email`, and `profile`. `drive.readonly`
is the narrowest practical scope that lets Memory discover, download, export, and incrementally track
accessible Drive files. Profile scopes are used only to associate the connection with a stable Google
account identifier and display email.

Initial sync lists supported files through Drive API pagination, upserts document metadata, exports
Google-native files to pipeline-supported formats, downloads supported uploaded files, hashes the
actual bytes, and calls the existing ingestion pipeline only when the indexed hash differs. The
changes cursor is persisted after the initial listing completes.

Incremental sync uses the Drive changes API from the stored cursor. Content changes trigger
download/export and re-ingestion. Renames, folder moves, and other metadata-only changes update
document metadata without re-embedding when the content hash is unchanged. Removed, inaccessible, or
trashed files are marked `deleted`, have chunks removed, and are excluded from search.

The current repository has no durable background worker. Drive sync endpoints therefore run the job
in-process while recording `sync_status`, summaries, and file failures in source/document metadata.
The next worker milestone should move the same service calls behind a queue with persisted
deduplication keys and exponential-backoff scheduling.

## Local Folder Synchronization

Local folder access is owned by the Tauri desktop shell. The backend never scans arbitrary local
paths; it receives typed uploads from approved roots. Desktop state persists approved roots, watcher
status, minimal known-file snapshots, and a durable pending-change queue in app data. Scans reconcile
the known snapshot against the current filesystem so missed deletes are tombstoned.

The backend uses the existing `Source` and `Document` abstractions. Local documents prefer platform
file IDs for stable identity across rename and move, with relative path as a fallback and user-facing
location. Content hashes decide whether extraction and embedding are skipped. Deletes remove chunks
and relationships in addition to marking documents deleted.

Details are documented in [LOCAL_FOLDERS.md](/Users/stephenlee/Software%20Projects/Memory/docs/LOCAL_FOLDERS.md).

## Retrieval

Search combines metadata constraints, pgvector cosine nearest-neighbor search, and a text-match signal over indexed chunks. The current implementation embeds queries on the backend, searches only chunks belonging to the requested user, and returns scored document-level results with excerpts and machine-readable signal explanations.

AI answers remain out of scope. Future answers must be grounded in retrieved chunks and include citations.

## Ingestion Pipeline

The ingestion pipeline accepts an existing document record plus file content, extracts text, normalizes block metadata, chunks deterministically, embeds chunks with the Gemini embeddings API, and stores chunk vectors in PostgreSQL. If the content hash matches the last indexed hash, ingestion records a skipped job and does not re-embed.

Supported initial file families:

- Plain text and Markdown.
- PDF.
- DOCX.
- PPTX.
- Common source-code formats.

## Isolation

All tables that contain user-owned data carry `user_id`. Future query builders must require user scope as a first-class argument rather than optional filtering.

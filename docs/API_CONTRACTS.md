# API Contracts

## Health

`GET /health`

```json
{
  "status": "ok",
  "service": "memory-api"
}
```

## Readiness

`GET /ready`

```json
{
  "status": "ready",
  "checks": {
    "database": true,
    "redis": true,
    "object_storage": true
  }
}
```

Readiness returns HTTP 200 with `not_ready` when dependencies fail so orchestrators can inspect individual checks.

## Authentication

`POST /auth/sign-in`

Creates or refreshes a backend user session and returns a signed bearer token. The current local app
uses passwordless email sign-in; production deployments should put this behind the chosen identity
provider before broad release.

Request:

```json
{ "email": "user@example.com", "display_name": "User" }
```

Response:

```json
{
  "access_token": "mem1...",
  "token_type": "bearer",
  "expires_in": 604800,
  "user_id": "00000000-0000-0000-0000-000000000001",
  "email": "user@example.com",
  "display_name": "User"
}
```

`GET /auth/me`

Returns the authenticated user for `Authorization: Bearer <token>`.

All source, ingestion, search, and Drive-management routes require a bearer token. Legacy `user_id`
fields may still be accepted for compatibility, but they must match the token subject.

## Search

`POST /search`

Request:

```json
{
  "user_id": "00000000-0000-0000-0000-000000000000",
  "query": "roadmap notes about onboarding",
  "limit": 10
}
```

The route requires `Authorization: Bearer <token>` and embeds the query on the backend. `GEMINI_API_KEY` is never part of the request or response.

Response:

```json
{
  "query": "roadmap notes about onboarding",
  "results": [
    {
      "document_id": "00000000-0000-0000-0000-000000000000",
      "title": "roadmap.md",
      "type": "text/markdown",
      "score": 0.82,
      "matching_excerpts": ["..."],
      "source_metadata": {
        "kind": "local_folder",
        "display_name": "Fixture Directory",
        "metadata": {},
        "document_metadata": {}
      },
      "explanation": {
        "final_score": 0.82,
        "semantic_score": 0.8,
        "text_score": 0.9,
        "matched_representation_type": "document_text",
        "has_extracted_text": true,
        "signals": [
          {
            "representation_id": "00000000-0000-0000-0000-000000000001",
            "chunk_id": "00000000-0000-0000-0000-000000000002",
            "type": "document_text",
            "score": 0.82,
            "raw_semantic_score": 0.8,
            "raw_text_score": 0.9,
            "matched_content": "...",
            "source_confidence": null,
            "embedding_model": "gemini-embedding-2",
            "embedding_model_version": "gemini-embedding-2",
            "extractor_version": "memory.extractors.v1",
            "applied_weight": 1.0,
            "configured_weight": 1.0,
            "adjustments": []
          }
        ]
      }
    }
  ]
}
```

Google Drive search results include `source_metadata.drive` when available:

```json
{
  "file_id": "drive-file-id",
  "web_url": "https://drive.google.com/...",
  "mime_type": "application/vnd.google-apps.document",
  "modified_time": "2026-07-26T12:00:00Z"
}
```

Every search route embeds the query on the backend, filters by `user_id`, searches
`search_representations`, and excludes deleted documents. Result explanations must identify the
matched representation type. UI labels should use `Document text`, `OCR text`, `Image description`,
`Filename`, `Folder or path`, `Metadata`, `Visual similarity`, or `Multiple signals`; visual,
filename, path, caption, and metadata matches must not be labeled as document-text matches.

Signal weights are configurable with `MEMORY_SEARCH_WEIGHT_DOCUMENT_TEXT`,
`MEMORY_SEARCH_WEIGHT_OCR_TEXT`, `MEMORY_SEARCH_WEIGHT_FILENAME`,
`MEMORY_SEARCH_WEIGHT_FILE_PATH`, `MEMORY_SEARCH_WEIGHT_METADATA`,
`MEMORY_SEARCH_WEIGHT_IMAGE_CAPTION`, `MEMORY_SEARCH_WEIGHT_VISUAL_EMBEDDING`,
`MEMORY_SEARCH_MIN_OCR_CONFIDENCE`, `MEMORY_SEARCH_STRONG_FILENAME_TEXT_RANK`,
`MEMORY_SEARCH_MIN_IMAGE_SINGLE_SIGNAL_SCORE`, and `MEMORY_SEARCH_INCLUDE_IMAGES`.
The default trust order is document text, high-confidence OCR, strong filename/path evidence, image
captions, and visual similarity for ordinary text queries. Low-confidence OCR and generic captions
are down-ranked by named policy values rather than silently becoming text matches.

Images are excluded from normal search results by default because legacy indexed image rows may have
weak or misleading textual provenance. Set `MEMORY_SEARCH_INCLUDE_IMAGES=true` only when image
retrieval has been deliberately enabled and inspected.

## Google Drive

All Google Drive management routes require a signed bearer token. `user_id` request/query values are
compatibility hints only and must match the token subject. OAuth secrets, authorization codes, access
tokens, refresh tokens, and encrypted credentials are never returned.

`POST /sources/google-drive/oauth/start`

Request:

```json
{ "user_id": "00000000-0000-0000-0000-000000000001" }
```

Response:

```json
{
  "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth?...",
  "state": "...",
  "status": "connecting"
}
```

`GET /sources/google-drive/oauth/callback`

Server-side OAuth callback for Google. It validates state and PKCE, exchanges the code server-side,
stores the refresh token encrypted at rest, and redirects to `GOOGLE_OAUTH_FRONTEND_RETURN_URL` with
a non-sensitive connection status query string.

`GET /sources/google-drive/status?user_id=...`

Returns connection state, connected account email, granted scopes, sync status, counts, the last sync
summary, and the last non-secret error message.

`POST /sources/google-drive/{source_id}/sync/initial`

`POST /sources/google-drive/{source_id}/sync/incremental`

Request:

```json
{ "user_id": "00000000-0000-0000-0000-000000000001" }
```

Response:

```json
{
  "source_id": "00000000-0000-0000-0000-000000000000",
  "summary": {
    "files_discovered": 12,
    "files_supported": 10,
    "files_indexed": 8,
    "files_unchanged": 1,
    "files_skipped": 1,
    "files_failed": 0,
    "files_deleted_or_removed": 2,
    "duration_seconds": 4.2,
    "additional_work_remains": false
  }
}
```

`POST /sources/google-drive/{source_id}/disconnect`

Removes local encrypted credentials and attempts to revoke Google access.

`GET /sources/google-drive/{source_id}/sync/status?user_id=...`

Returns the same shape as the connection status route for a specific source.

`GET /sources/google-drive/{source_id}/sync/summary?user_id=...`

Returns the last persisted synchronization summary.

`GET /sources/google-drive/{source_id}/failures?user_id=...`

Lists failed Drive documents for inspection without file contents.

`POST /sources/google-drive/{source_id}/failures/{document_id}/retry`

Retries by running an incremental sync for the source. A later worker milestone should narrow this
to single-file job dispatch once a queue exists.

`GET /sources/google-drive/documents/{document_id}/open?user_id=...`

Returns the original Google Drive web URL for an active document owned by the user.

## Local Folders

`POST /sources/local-folders`

Registers or updates a selected desktop folder as a `local_folder` source. The desktop sends a root
fingerprint rather than exposing the absolute path through the backend API.

`POST /sources/local-folders/{source_id}/files`

Uploads one approved local file for ingestion. The backend verifies `source_id`, `user_id`, payload
size, and SHA-256 content hash before calling the existing ingestion pipeline. `platform_file_id` is
preferred as the stable document identity; relative path remains user-facing metadata and a fallback
identity.

Additional fields:

```json
{
  "platform_file_id": "device:inode",
  "metadata_only": false
}
```

Metadata-only files are sent as generated text metadata and marked with `content_indexed: false`.
`MEMORY_LOCAL_MAX_UPLOAD_BYTES` enforces the backend upload limit.

`POST /sources/local-folders/{source_id}/delete`

Marks a local document deleted, removes its chunks and relationships, and excludes it from active
search. Requests may include `platform_file_id` for stable identity and `recursive: true` for folder
deletion reconciliation.

`PATCH /sources/local-folders/{source_id}/status`

Updates non-secret scan and watcher status fields for the source. All local-folder routes are scoped
by the signed bearer token and `source_id`.

## Planned Contracts

- `POST /sources/{source_id}/sync`
- `GET /documents`
- `GET /documents/{document_id}`
- `GET /graph`
- `POST /answers`

These routes are not implemented in milestone one.

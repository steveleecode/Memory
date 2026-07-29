# Data Model

## Users

`users` stores account identity and profile metadata.

## Sources

`sources` stores connected Google Drive accounts and local folders. OAuth credentials are stored only as encrypted bytes. `sync_cursor` supports incremental Google Drive sync and local folder snapshots.

For Google Drive, `external_id` is the Google account identifier after connection. Pending OAuth
connections temporarily use an `oauth:{nonce}` identity until the callback succeeds. `source_metadata`
stores non-secret account and synchronization state:

- `google_account_identifier`
- `google_account_email`
- `granted_scopes`
- `initial_synchronization_status`
- `last_successful_synchronization_time`
- `last_synchronization_error`
- `last_synchronization_summary`
- `sync_status`

`encrypted_credentials` stores an encrypted JSON payload containing the refresh token and granted
scope set. Plaintext access and refresh tokens are never stored.

## Documents

`documents` stores source file identity, content hashes, object keys, extraction status, optional document embedding, stable graph coordinates, searchable representation text, indexed content hash, and the latest ingestion error.

For local folders, document identity prefers `platform:{platform_file_id}` when the desktop can
provide one and falls back to `path:{relative_path}`. `document_metadata` preserves relative path,
filename, extension, size, timestamps, parent directory, platform file ID, source ID, indexing state,
and whether the record is metadata-only. Deleted local files are tombstoned and have chunks and
relationships removed so they are not searchable.

For Google Drive documents, `external_id` is the Drive file ID. `document_metadata` stores non-secret
Drive metadata such as filename, Drive MIME type, parent folder IDs, created and modified times,
size, checksum, web URL, trash state, shared/owned flags, version, revision ID, indexing state, and
the source type. Deleted, trashed, or inaccessible files are tombstoned with `status = deleted` and
their chunks are removed so stale embeddings are not searchable.

## Document Chunks

`document_chunks` stores normalized extracted text slices with chunk ordinals, token counts, content hashes, metadata, and chunk embeddings.

## Ingestion Jobs

`ingestion_jobs` records retry-safe ingestion attempts. Status values are pending, running, succeeded, failed, and skipped. Failure code and message fields preserve useful operational detail without exposing file content in logs.

## Relationships

`document_relationships` stores weighted directed edges between documents. Initial planned edge types are semantic similarity, shared source, explicit reference, and temporal neighbor.

## Embeddings

The initial migration enables pgvector and reserves `vector(1536)` columns for document-level and chunk-level embeddings. Milestone two stores real Gemini chunk embeddings and a document-level searchable representation generated from filename, metadata, headings, and extracted content.

## Object Storage Keys

Future S3 keys should include user and source scope, for example:

```text
users/{user_id}/sources/{source_id}/documents/{document_id}/original
users/{user_id}/sources/{source_id}/documents/{document_id}/extracted.txt
```

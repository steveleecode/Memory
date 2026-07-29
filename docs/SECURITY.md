# Security

## Sensitive Data

- OAuth refresh tokens and access tokens.
- Local folder paths.
- Original files.
- Extracted text.
- Embeddings.
- Retrieved chunks and answer traces.

## Credential Encryption

OAuth credentials must be encrypted before persistence. Production should use envelope encryption with a cloud KMS or platform keychain. Local development uses a placeholder setting only to keep configuration explicit.

Google Drive refresh tokens are encrypted with `OAUTH_CREDENTIAL_ENCRYPTION_KEY` before being stored
in `sources.encrypted_credentials`. The frontend never receives the client secret, authorization
code, access token, refresh token, encrypted credential payload, file content, or extracted text.
Use a Fernet key or KMS-derived secret in production; the repository default is development-only and
must not be reused for real users.

## Data Isolation

- Every user-owned table includes `user_id`.
- Protected API routes derive user scope from signed bearer tokens.
- Google Drive sources are selected by both `source_id` and `user_id`.
- Object storage keys must include user scope.
- Redis keys must include user scope where user data is represented.
- Logs must not include extracted text, OAuth tokens, or full local paths.

## Google OAuth

The Drive connector uses a server-side authorization-code flow with PKCE and a cryptographically
random state nonce. The requested scopes are `https://www.googleapis.com/auth/drive.readonly`,
`openid`, `email`, and `profile`. Revoked credentials transition the source to
`reauthorization_required`; disconnect removes local credentials and attempts Google token
revocation. Do not log OAuth callback query strings because they can contain authorization codes.

## Local Folder Access

Tauri must request explicit folder selection. The backend should receive stable source identity and extracted artifacts through a narrow desktop bridge rather than broad filesystem access.

The desktop app uses native folder selection and stores approved canonical roots only in local app
data. Open, reveal, scan, and upload commands reject absolute child paths, reject `..` traversal,
canonicalize existing files, and refuse symlinks that resolve outside the approved root. Ordinary
backend responses expose relative paths, not absolute local paths.

Pending local changes are stored as relative path, event kind, timestamp, platform file ID when
available, and recursive-delete flag. File contents are not stored in the local retry queue.

## Application Authentication

The backend installs authentication middleware that parses `Authorization: Bearer <token>` and
exposes the token subject to protected route dependencies. Tokens are HMAC-SHA256 signed with
`MEMORY_AUTH_TOKEN_SECRET` and include subject, email, issued-at time, and expiry. Source, ingestion,
search, and Drive-management routes use the token subject as the authoritative user ID; legacy
`user_id` fields must match or the request is rejected.

The current local app has passwordless email sign-in for development. Production should connect this
session issuance to the selected identity provider and rotate `MEMORY_AUTH_TOKEN_SECRET` through a
secret manager.

## Development Mocks

Mocks are disabled by default. Any mock connector, document, answer, or embedding provider must require `MEMORY_ENABLE_DEVELOPMENT_MOCKS=true` and must be visibly labeled.

## Embedding API Keys

`GEMINI_API_KEY` is read only by the FastAPI backend and CLI. It must not be exposed through frontend environment variables, bundled web code, Tauri commands, source metadata, logs, or API responses.

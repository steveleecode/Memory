# Production Readiness

This checklist captures work that must be completed after local development milestones and before
Memory is released with real users or sensitive data.

## Authentication

The current backend has real signed bearer-token middleware, but `/auth/sign-in` is a local
passwordless email flow for development. Before production:

- Connect `/auth/sign-in` to the selected identity provider.
- Verify the provider-issued identity server-side before minting a Memory session token.
- Decide the supported provider model: hosted OAuth/OIDC, passkeys, enterprise SSO, or a combination.
- Store provider subject IDs on users so email changes do not break account identity.
- Enforce verified email where the provider supports it.
- Add logout/session revocation semantics.
- Add token rotation and secret rotation procedures for `MEMORY_AUTH_TOKEN_SECRET`.
- Move auth secrets into a production secret manager.
- Add rate limiting and abuse controls to sign-in endpoints.
- Add integration tests for invalid, expired, revoked, and cross-user tokens.
- Update desktop and web sign-in UX to reflect the production provider.

Do not ship the development email-only sign-in as production authentication.

## Secrets And Credentials

- Replace development OAuth and auth secrets with production-managed secrets.
- Use KMS or equivalent envelope encryption for OAuth refresh tokens.
- Confirm no access tokens, refresh tokens, authorization codes, client secrets, file contents, or
  absolute local paths are logged.
- Document incident response for leaked tokens or signing keys.

## Data Isolation

- Audit every API route for authenticated user scope.
- Confirm source, document, chunk, job, cache, object-storage, and queue keys include user scope.
- Add regression tests for cross-user source, document, Drive, and local-folder access attempts.

## Background Jobs

- Move Drive and local indexing work behind a durable queue.
- Add persisted deduplication keys, exponential backoff, cancellation, and job ownership checks.
- Ensure failed file jobs do not fail full source sync unless credentials/source state are invalid.

## Deployment Verification

- Run migrations from a clean database.
- Run backend, frontend, desktop, Rust, and integration test suites in CI.
- Run real Google Drive verification with a test account.
- Run real desktop local-folder verification on macOS, Windows, and Linux.
- Confirm deleted Drive and local files disappear from active search.
- Confirm unchanged content is not re-embedded on repeat sync.

## Documentation

- Replace local-development auth instructions with production provider setup.
- Document provider callback URLs, allowed origins, token lifetimes, and logout behavior.
- Keep local-development setup clearly labeled as non-production.

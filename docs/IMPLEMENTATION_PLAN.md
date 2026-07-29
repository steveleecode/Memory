# Implementation Plan

## Milestone One

- Scaffold pnpm monorepo.
- Add web and desktop app shells.
- Add shared UI and TypeScript contract packages.
- Add FastAPI health/readiness endpoints.
- Add PostgreSQL, pgvector, Redis, and MinIO local services.
- Add initial SQLAlchemy models and Alembic migration.
- Add backend tests.
- Add product, experience, architecture, data, API, security, and design docs.

## Recommended Milestone Two

Implemented source ingestion and search foundations:

- File extraction for text, Markdown, PDF, DOCX, PPTX, and source code.
- Deterministic token-aware chunking.
- Gemini embedding generation in the backend.
- Idempotent content-hash checks to skip unchanged content.
- PostgreSQL/pgvector chunk storage and cosine retrieval.
- Basic hybrid ranking with semantic and text signals.
- CLI ingestion and search commands.

## Recommended Milestone Three

Build source connection foundations without folder watching:

- Add authentication boundary and user session model.
- Implement encrypted credential service.
- Implement Google OAuth start/callback behind real provider configuration.
- Add Tauri local-folder permission bridge returning selected folder metadata only.
- Add source CRUD and source status APIs.
- Add repository layer that enforces `user_id` on every query.
- Add integration tests for source isolation and credential encryption.

## Later Milestones

- Incremental sync workers.
- Text extraction pipeline.
- Chunking and embedding providers.
- Hybrid search and answer grounding.
- Relationship generation.
- Stable spatial graph.

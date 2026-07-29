# Product Spec

## Vision

Memory gives users a private, trustworthy way to find and understand their own files. It combines connected cloud storage, selected local folders, semantic retrieval, and a restrained spatial exploration surface.

## Users

- Knowledge workers with scattered documents across Drive and local folders.
- Founders, researchers, writers, and operators who need recall across projects.
- Privacy-sensitive users who need clear boundaries around indexed content.

## Core Jobs

- Connect a source intentionally.
- See what is being indexed and whether it is current.
- Search in natural language.
- Inspect retrieved documents and grounded answer citations.
- Explore related files without losing orientation.

## Non-Goals For Milestone One

- Google OAuth implementation.
- Local-folder selection or indexing.
- Embedding generation.
- AI answers.
- Spatial graph UI.
- Operational mock data.

## Product Requirements

- Every source belongs to one user.
- Users can pause, revoke, and resync sources in future milestones.
- Search must distinguish exact, semantic, and answer modes.
- AI answers must cite file chunks and expose uncertainty.
- Development mocks must require `MEMORY_ENABLE_DEVELOPMENT_MOCKS=true`.

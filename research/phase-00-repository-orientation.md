# Phase 00: Repository Orientation

## Goal

Map the current Memory architecture before changing behavior. This phase prevents the research platform from duplicating existing ingestion, storage, retrieval, authentication, or UI abstractions.

## Scope

- Inspect API routes, models, ingestion pipeline, search service, CLI, shared types, web UI, desktop shell, and documentation.
- Identify the current retrieval path from indexed chunks to user-visible search results.
- Identify where answer-generation hooks exist or are still frontend-only.
- Record configuration, testing, linting, and migration conventions.
- Confirm privacy boundaries for user identity, source ownership, document text, embeddings, and logs.

## Expected Outputs

- A concise architecture note in this directory or `docs/` that links product components to future research extension points.
- A list of concrete files that will be touched by the next phase.
- A short risk note covering tenant isolation and production-data exposure.

## Acceptance Criteria

- The current ingestion, storage, retrieval, and UI paths are documented.
- Existing conventions for Python, TypeScript, tests, migrations, and package scripts are identified.
- No product behavior changes are made in this phase.
- No synthetic results or incomplete research features are presented as working functionality.

## Validation

- Run read-only inspection commands such as `rg`, `find`, and existing test discovery.
- If code is not changed, no runtime tests are required.

## Commit

Use a documentation-only commit such as:

```text
docs(research): document current retrieval architecture
```

# Phase 07: Privacy, Authorization, and Test Hardening

## Goal

Harden the research platform so it preserves Memory's private-search trust boundary while expanding test coverage around retrieval experiments.

## Privacy Requirements

- Preserve strict per-user isolation.
- Do not place raw user documents in repository fixtures.
- Do not upload private data to third-party evaluation services without explicit configuration and consent.
- Do not log document contents in normal application logs.
- Do not mix data from different users.
- Do not use production user activity as research data by default.
- Synthetic benchmark data remains the default.

## Future Consented Study Documentation

Document how a future consented study could export de-identified research snapshots without modifying production records. The documentation should cover:

- User consent.
- De-identification boundaries.
- Snapshot immutability.
- Dataset provenance.
- Retention and deletion.
- Review requirements before external sharing.

## Required Test Areas

- Retrieval strategy conformance.
- Score normalization.
- Temporal decay.
- Historical versus recent query handling.
- Deterministic seeded execution.
- Dataset validation.
- Metric correctness with hand-calculated examples.
- Experiment configuration validation.
- Run artifact generation.
- Tenant isolation.
- Authorization for research routes.
- Missing timestamps.
- Failed queries.

## Acceptance Criteria

- Tests cover product and research boundary conditions.
- No tests rely only on snapshots.
- Sensitive fields are absent from normal logs and committed fixtures.
- Research fixtures are labeled synthetic.
- CI checks pass.

## Commit

```text
test: expand research platform coverage
```

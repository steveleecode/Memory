# Memory Research Development Plan

This directory plans the phased Codex development work for evolving Memory into a dual-purpose product and research platform for long-term AI memory and retrieval experiments.

These files are planning artifacts only. They do not claim that research infrastructure, strategies, metrics, dashboard routes, or experiment results already exist. Each phase should be implemented as a small, reviewable feature with tests, documentation updates, and a focused commit before starting the next phase.

## Research Question

The first concrete research question is:

> Does query-dependent temporal weighting improve retrieval quality for temporally situated personal-information queries without degrading performance on temporally neutral queries?

The goal is to build infrastructure to test this question. The project must not claim the hypothesis is true without validated evidence.

## Product Boundaries

Memory remains a production-quality private semantic search product. Research work must preserve:

- Google Drive and local-folder ingestion.
- Document extraction, chunking, embeddings, and storage.
- Semantic search and answer workflows.
- Authentication and strict per-user isolation.
- The polished user-facing product experience.

Research features must be modular, private, authenticated, and disabled or hidden from ordinary users unless explicitly enabled.

## Phase Index

- [Phase 00: Repository Orientation](phase-00-repository-orientation.md)
- [Phase 01: Retrieval Strategy Foundation](phase-01-retrieval-strategy-foundation.md)
- [Phase 02: Baseline and Temporal Strategies](phase-02-baseline-and-temporal-strategies.md)
- [Phase 03: Versioned Research Datasets](phase-03-versioned-research-datasets.md)
- [Phase 04: Experiment Configuration and Runner](phase-04-experiment-configuration-and-runner.md)
- [Phase 05: Metrics and Reproducible Artifacts](phase-05-metrics-and-artifacts.md)
- [Phase 06: Research Dashboard and Inspector](phase-06-dashboard-and-inspector.md)
- [Phase 07: Privacy, Authorization, and Test Hardening](phase-07-privacy-and-test-hardening.md)
- [Phase 08: Initial Temporal Retrieval Study](phase-08-initial-temporal-retrieval-study.md)
- [Phase 09: Roadmap and Release Boundary](phase-09-roadmap-and-release-boundary.md)

## Development Rules

- Use synthetic benchmark data by default.
- Do not place raw user documents, personal file paths, embeddings, OAuth credentials, or answer traces in fixtures.
- Do not silently use production data as a research dataset.
- Keep research datasets immutable once versioned.
- Store predicted temporal intent separately from human-labeled query category.
- Record failures instead of dropping failed examples.
- Label demonstration results as engineering validation, not scientific evidence.

## Suggested Commit Sequence

1. `docs(research): add phased research development plan`
2. `refactor: introduce retrieval strategy interface`
3. `feat: add lexical and temporal retrieval strategies`
4. `feat: add versioned research dataset schema`
5. `feat: add experiment configuration and runner`
6. `feat: add retrieval evaluation metrics`
7. `feat: persist reproducible experiment artifacts`
8. `feat: add research dashboard`
9. `test: expand research platform coverage`
10. `docs: document memory research workflows`

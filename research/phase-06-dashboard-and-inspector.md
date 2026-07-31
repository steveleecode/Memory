# Phase 06: Research Dashboard and Inspector

## Goal

Add private, authenticated research UI routes for inspecting datasets, experiments, runs, comparisons, and retrieval score details.

## Routes

Suggested route shape:

```text
/research
/research/datasets
/research/experiments
/research/runs/:id
/research/comparisons
```

## Dashboard Capabilities

- View datasets and versions.
- Inspect experiment configurations.
- Browse runs.
- Compare strategies.
- Filter by query category.
- Inspect individual failures.
- View retrieved chunks and score components.
- Export structured results.

## Retrieval Inspector

Add an optional development-only inspector to search results. When enabled, show score components such as:

- Semantic score.
- Lexical score.
- Temporal score.
- Predicted temporal intent.
- Project or hierarchy signal.
- Final combined score.
- Rank.

The inspector must be disabled by default in production.

## Acceptance Criteria

- Research routes require authentication and explicit research access.
- Ordinary users do not see research routes by default.
- UI remains visually consistent with Memory.
- Retrieved chunks shown in the dashboard come from approved synthetic datasets or authorized research artifacts, not arbitrary production data.
- Inspector controls are environment-gated and clearly development-only.

## Test Coverage

- Research route authorization.
- Disabled route visibility for ordinary users.
- Run list rendering.
- Category filtering.
- Failure inspection.
- Inspector disabled in production configuration.

## Commit

```text
feat: add research dashboard
```

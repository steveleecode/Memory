# Phase 05: Metrics and Reproducible Artifacts

## Goal

Compute standard retrieval metrics and persist complete run artifacts for reproducibility and comparison.

## Required Metrics

- Recall@k.
- Precision@k.
- Mean Reciprocal Rank.
- NDCG@k.
- Latency.
- Number of chunks retrieved.
- Number of context tokens retrieved.

## Extensible Answer Metrics

When expected answers or rubrics exist, support extension points for:

- Exact match.
- Token-level F1.
- Citation precision.
- Citation recall.
- Unsupported-claim rate.
- Rubric-based human grading.

LLM judgment must never be the only source of truth. If model-based evaluation is added, record model, prompt, settings, and raw judgment.

## Artifact Layout

Use a structured output such as:

```text
research/results/<experiment>/<run-id>/
├── manifest.json
├── config.yaml
├── raw_retrieval.jsonl
├── answers.jsonl
├── per_query_metrics.jsonl
├── aggregate_metrics.json
├── failures.jsonl
└── report.md
```

## Manifest Requirements

Every run should save:

- Unique run ID.
- Timestamp.
- Experiment configuration.
- Dataset version.
- Code commit hash when available.
- Dirty-working-tree status.
- Strategy versions.
- Model names.
- Package or environment metadata.
- Random seeds.
- Raw retrieval outputs.
- Raw generated answers when enabled.
- Per-query metrics.
- Aggregate metrics.
- Failures and warnings.

## Acceptance Criteria

- Metrics match hand-calculated examples.
- Aggregate reports include all queries, each query category, each seed, and each strategy.
- Tiny demonstration datasets do not produce misleading significance claims.
- Confidence intervals are reported only when sample size supports them.

## Test Coverage

- Recall@k and precision@k.
- MRR.
- NDCG@k.
- Empty relevance sets.
- Duplicate retrieved IDs.
- Missing chunks.
- Artifact generation.
- Dirty tree and commit hash recording.

## Commit

```text
feat: add retrieval evaluation metrics
```

Follow with:

```text
feat: persist reproducible experiment artifacts
```

# Phase 08: Initial Temporal Retrieval Study

## Goal

Run the first engineering-validation experiment on the synthetic demonstration dataset.

## Initial Experiment

Create an experiment file matching the implemented schema. The conceptual configuration is:

```yaml
name: temporal_retrieval_v1
hypothesis: >
  Query-dependent temporal weighting improves retrieval quality for
  temporally situated queries without degrading temporally neutral queries.
strategies:
  - semantic
  - semantic_fixed_recency
  - semantic_query_temporal
metrics:
  - recall_at_5
  - recall_at_10
  - precision_at_5
  - mrr
  - ndcg_at_10
  - latency_ms
  - retrieved_tokens
```

Complete the exact schema based on the implemented runner and validation model.

## Run Requirements

- Run only on the synthetic demonstration dataset.
- Generate run artifacts and a report.
- Label results as engineering validation, not scientific evidence.
- Do not claim statistical significance from the tiny demonstration dataset.
- Include all failures and warnings.

## Report Contents

- Run ID.
- Dataset ID and version.
- Strategy versions and parameters.
- Query category breakdown.
- Aggregate metrics.
- Per-query failure summary.
- Known limitations.
- Next recommended research milestone.

## Acceptance Criteria

- The experiment runs end-to-end.
- Artifacts are persisted under the agreed results layout.
- The report can be inspected from the research dashboard or opened directly.
- Demonstration language avoids unsupported claims.

## Commit

```text
docs: document memory research workflows
```

If the experiment file and generated demonstration artifacts are committed, keep them separate from unrelated implementation changes and ensure they contain no private data.

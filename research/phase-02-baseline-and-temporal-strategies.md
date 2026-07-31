# Phase 02: Baseline and Temporal Strategies

## Goal

Add initial interchangeable retrieval strategies for baseline comparison and the first temporal research question.

## Strategies

- `semantic`: existing semantic retriever behind the common interface.
- `keyword`: lexical baseline using a database-native or established lexical search implementation.
- `semantic_fixed_recency`: semantic relevance combined with configurable time decay.
- `semantic_query_temporal`: semantic relevance combined with query-dependent temporal weighting.

## Temporal Query Taxonomy

Represent query categories explicitly:

- `explicit_temporal`
- `implicit_temporal`
- `temporally_neutral`
- `historical`
- `ambiguous`

Human labels belong in benchmark data. Predicted temporal intent belongs in strategy outputs or run artifacts so classification errors can be measured separately from retrieval quality.

## Scoring Requirements

The inspectable first scoring formula should resemble:

```text
final_score =
  semantic_weight * normalized_semantic_score
  + temporal_weight(query) * temporal_relevance
```

All weights, time-decay parameters, and temporal-intent thresholds must be configurable and documented. Historical intent must be supported; queries such as "original architecture" should not automatically favor recent files.

## Acceptance Criteria

- Each strategy implements the shared interface.
- Each strategy exposes name, version, and serializable configuration.
- Component scores are returned when available.
- Missing timestamps are handled gracefully.
- Temporal parsing or classification is deterministic by default for the first implementation.
- Strategy outputs remain tenant-isolated.

## Test Coverage

- Score normalization.
- Fixed recency decay.
- Historical versus recent query handling.
- Ambiguous and temporally neutral query handling.
- Missing timestamps.
- Seeded deterministic execution.
- Keyword strategy ranking on hand-built fixtures.

## Commit

```text
feat: add lexical and temporal retrieval strategies
```

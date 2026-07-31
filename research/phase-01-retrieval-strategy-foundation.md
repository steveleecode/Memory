# Phase 01: Retrieval Strategy Foundation

## Goal

Refactor retrieval behind a shared, typed strategy interface without changing the normal search experience.

## Scope

- Define a retrieval request object shared by all strategies.
- Define a retrieval response object with ranked document and chunk identifiers.
- Include optional score components, timing metadata, strategy name, strategy version, and serializable configuration.
- Add a strategy registry so strategies are selected explicitly rather than through scattered conditionals.
- Wrap the existing semantic retriever as the initial `semantic` strategy.
- Preserve the existing `/search` contract unless a versioned extension is required.

## Non-Goals

- Do not add temporal scoring yet.
- Do not build the experiment runner yet.
- Do not change user-facing ranking behavior except where required by the refactor, and document any unavoidable difference.

## Design Notes

The conceptual shape is:

```python
class RetrievalStrategy(Protocol):
    name: str
    version: str

    async def retrieve(
        self,
        request: RetrievalRequest,
        context: RetrievalContext,
    ) -> RetrievalResponse:
        ...
```

Adapt the exact implementation to the existing FastAPI, SQLAlchemy, and typing conventions.

## Acceptance Criteria

- Existing semantic search runs through the registry-backed `semantic` strategy.
- Strategy selection is explicit and validated.
- Responses include identifiers, scores where available, and timing metadata.
- Deterministic dependencies can accept a seed.
- Existing API tests still pass.

## Test Coverage

- Strategy conformance.
- Registry lookup and unknown-strategy errors.
- Compatibility with existing search responses.
- Tenant isolation in retrieval queries.
- Deterministic behavior with seeded test dependencies where applicable.

## Commit

```text
refactor: introduce retrieval strategy interface
```

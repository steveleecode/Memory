# Phase 04: Experiment Configuration and Runner

## Goal

Support declarative experiments and a command-line runner that executes configured strategies over immutable dataset versions.

## Desired Workflow

Use this command shape unless repository conventions suggest a better one:

```bash
pnpm research validate experiments/temporal_retrieval_v1.yaml
pnpm research run experiments/temporal_retrieval_v1.yaml
pnpm research compare temporal_retrieval_v1
```

## Experiment Configuration

Each configuration should specify:

- Name.
- Hypothesis.
- Dataset ID and version.
- Retrieval strategies.
- Strategy parameters.
- Evaluation metrics.
- Top-k values.
- Optional answer-generation configuration.
- Random seeds.
- Output location.

## Runner Requirements

- Load an immutable dataset version.
- Execute every configured strategy on every test query.
- Save raw ranked results.
- Optionally generate answers from retrieved context.
- Compute metrics.
- Aggregate results by strategy and query category.
- Preserve per-query results.
- Record partial failures without silently dropping examples.
- Fail configuration validation with actionable errors before execution.

## Acceptance Criteria

- Invalid experiment files fail before a run starts.
- Each query and strategy pair has either a result or a recorded failure.
- Runs can be repeated with a fixed seed.
- The runner does not use production user data by default.

## Test Coverage

- Experiment configuration validation.
- Unknown dataset version.
- Unknown strategy.
- Invalid metric.
- Failed query handling.
- Deterministic seeded execution.

## Commit

```text
feat: add experiment configuration and runner
```

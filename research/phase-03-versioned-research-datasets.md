# Phase 03: Versioned Research Datasets

## Goal

Create a versioned dataset format and a small synthetic demonstration dataset that can exercise the full research pipeline without exposing real user data.

## Dataset Schema

Each dataset version should include:

- Dataset ID and version.
- Collection metadata.
- Documents or references to immutable document snapshots.
- Chunks.
- Document metadata.
- Timestamps.
- Project and folder relationships.
- Test queries.
- Human-labeled query categories.
- Relevant document IDs.
- Relevant chunk IDs where available.
- Expected answers or grading rubrics where available.
- Train, validation, and test split.
- Provenance and licensing notes.

## Synthetic Demonstration Dataset

The first dataset should model several fictional projects with:

- Old and new document versions.
- Overlapping terminology across projects.
- Folders and project relationships.
- Notes with temporal references.
- Explicit temporal, implicit temporal, neutral, historical, and ambiguous queries.

The dataset must be clearly labeled as synthetic and insufficient for substantive research conclusions.

## Acceptance Criteria

- Dataset schema is validated before use.
- Dataset versions are immutable by convention and path.
- Synthetic fixtures contain no real user data.
- Human labels and predicted intent fields are stored separately.
- Validation errors identify the dataset path and failing field.

## Test Coverage

- Dataset validation success and failure cases.
- Duplicate IDs.
- Missing relevant documents or chunks.
- Invalid query categories.
- Split validation.
- Timestamp parsing.

## Commit

```text
feat: add versioned research dataset schema
```

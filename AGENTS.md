# Memory Agent Guide

Memory is a production-quality application for private semantic file search across Google Drive and user-selected local folders. Work should preserve user trust above speed.

## Principles

- Do not ship mock functionality that looks operational.
- Development mocks must be isolated behind `MEMORY_ENABLE_DEVELOPMENT_MOCKS=true` and labeled in UI or logs.
- Keep strict per-user data isolation in API queries, storage keys, embeddings, caches, jobs, and logs.
- Treat OAuth credentials, local file paths, extracted text, embeddings, and answer traces as sensitive.
- Prefer small, reviewable changes that follow the monorepo structure.

## Feature Completion and Git Commits

A Git commit must be created after the completion of every feature.

A feature is complete only when:

- Its stated requirements and acceptance criteria are satisfied.
- The implementation is functional and does not rely on unlabeled mock behavior.
- Relevant tests have been added or updated.
- Existing tests continue to pass.
- Formatting, linting, and type checks pass.
- Relevant documentation has been updated.
- The final diff has been reviewed for accidental or unrelated changes._

After completing and verifying a feature:

- Review the complete Git diff.
- Stage only files related to that feature.
- Create a descriptive Git commit for the completed feature.
- Use a conventional commit message when practical, such as:
- feat(api): add readiness endpoint
- feat(indexing): persist indexed documents
- fix(auth): enforce per-user token isolation
- test(api): add health endpoint coverage
- docs(architecture): document local service setup
- Confirm that the working tree contains no unintended changes before beginning the next feature.

Do not begin another feature before committing the completed feature.

Do not:

- Commit incomplete or knowingly broken features.
- Combine multiple unrelated features into one commit.
- Include secrets, credentials, .env files, private file contents, or sensitive user data in a commit.
- Disable tests or weaken validation only to make checks pass.
- Rewrite, squash, amend, force-push, or delete existing commits unless explicitly instructed.
- Push directly to a protected branch unless explicitly instructed.

If a feature cannot be completed because of missing requirements, unavailable credentials, failing infrastructure, or another blocker, do not create a misleading completion commit. Clearly report the blocker and leave the work uncommitted unless explicitly asked to create a work-in-progress commit.

## GitHub Workflow

The GitHub CLI (`gh`) is installed and authenticated.

Before beginning work:

1. Run `gh issue list` to view open issues.
2. Claim the issue you are working on by commenting on it.
3. Read the complete issue with:
   ```bash
   gh issue view <issue-number>
   ```
4. Treat the GitHub issue description as the implementation specification.
5. If requirements are unclear, ask for clarification instead of guessing.

When implementing:

- Reference the issue number in commits.
- Create a dedicated branch:
  ```bash
  git checkout -b issue-<number>-short-description
  ```
- Make small, reviewable commits.
- Run all tests and linting before committing.
- Open a pull request when the issue is complete:
  ```bash
  gh pr create
  ```

After completion:

- Comment on the issue summarizing what was implemented.
- Link the PR to the issue.

## Parallel Development

Each Codex instance should:

- Select exactly one open GitHub issue.
- Work only on that issue.
- Never modify files unrelated to that issue unless necessary.
- Commit progress frequently.
- Open a PR linked to the issue.
- Do not begin another issue after finishing unless instructed.

## Commands

- Install JS dependencies: `pnpm install`
- Check JS formatting/lint/types: `pnpm check`
- Create API venv: `python3 -m venv .venv`
- Install API dependencies: `.venv/bin/pip install -e "apps/api[dev]"`
- Start local services: `docker compose -f infrastructure/docker-compose.yml up -d`
- Run migrations: `cd apps/api && ../../.venv/bin/alembic upgrade head`
- Run API tests: `.venv/bin/pytest apps/api`

## Milestone Boundary

This milestone includes scaffolding, docs, local services, API health/readiness, initial models, migrations, and tests. It does not include Google OAuth, local folder indexing, embeddings, AI answers, or spatial graph UI.

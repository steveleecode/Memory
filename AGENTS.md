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
2. Select the issue that matches the user-assigned work. If no open issue matches a direct user request, record that no applicable issue exists and proceed without claiming an unrelated issue.
3. Claim the issue you are working on by commenting on it when an applicable issue exists.
4. Read the complete issue with:
   ```bash
   gh issue view <issue-number>
   ```
5. Treat the GitHub issue description as the implementation specification when an applicable issue exists. For directly assigned no-issue work, treat the user's request as the implementation specification.
6. If requirements are unclear, ask for clarification instead of guessing.

When implementing:

- Reference the issue number in commits.
- Reference `no-issue` in commits when directly assigned work has no applicable issue.
- Create a dedicated branch for new issue work:
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

- Comment on the issue summarizing what was implemented when an applicable issue exists.
- Link the PR to the issue when an applicable issue exists.

## Parallel Development

Each Codex instance should:

- Select exactly one open GitHub issue.
- Work only on that issue.
- Never modify files unrelated to that issue unless necessary.
- Commit progress frequently.
- Open a PR linked to the issue.
- Do not begin another issue after finishing unless instructed.

## Required Push and Pull Request

Unless the user explicitly requests local-only work, a task that modifies the repository is **not complete** after creating a local Git commit.

A task is only considered complete when all of the following have succeeded:

- The feature has been committed.
- The feature branch has been pushed to GitHub.
- A GitHub pull request has been created.
- The issue is linked in the pull request (for example, `Closes #123`) when an applicable issue exists, or the pull request clearly states that it is directly assigned no-issue work.
- The pull request URL is included in the final response.

After creating the final commit, execute the following workflow:

```bash
BRANCH="$(git branch --show-current)"

git push --set-upstream origin "$BRANCH"

gh pr create \
  --fill \
  --head "$BRANCH"
```

If `gh pr create` requires additional information, provide it non-interactively using the appropriate flags (`--title`, `--body`, `--base`, `--head`, `--draft`, etc.). Do **not** stop because the command is interactive.

If the branch has not yet been pushed, push it before attempting to create a pull request.

If `git push` or `gh pr create` fails:

- Read and diagnose the exact error.
- Attempt reasonable fixes (authentication, upstream branch, remote configuration, etc.).
- If the error cannot be resolved, report the exact blocker.
- Do **not** report the task as complete without a successfully created pull request.

The final response for every completed GitHub issue must include:

- Branch name
- Commit SHA
- Pull request URL
- Tests/checks that were run
- Any remaining known limitations

## CI Failure Investigation

When assigned a CI failure:

- Use `gh run view <run-id> --log-failed` to inspect failed logs.
- Inspect the exact commit that triggered the failure.
- Reproduce the failing command locally when possible.
- Identify the root cause before editing code.
- Make the smallest correct change.
- Never disable, skip, loosen, or delete a legitimate test solely to pass CI.
- Run all directly affected tests, lint checks, and type checks.
- Commit the completed fix and open a draft pull request.
- Include the workflow run URL and failure explanation in the pull request.

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

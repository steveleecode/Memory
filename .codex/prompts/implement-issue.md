# Implement GitHub Issue

Implement the GitHub issue provided as `$ARGUMENTS`.

Examples:

```bash
/implement-issue 12
/implement-issue #12
```

## Objective

Fully implement the selected GitHub issue, verify the work, push the feature branch, and open a pull request.

A local commit alone does not complete this task.

## Workflow

### 1. Verify the environment

Run:

```bash
git status
git remote -v
gh auth status
gh repo view --json nameWithOwner,defaultBranchRef
```

Stop and clearly report the blocker if:

* This is not a Git repository.
* The GitHub remote is unavailable.
* `gh` is not authenticated.
* The repository cannot be accessed.

### 2. Resolve the issue number

Interpret `$ARGUMENTS` as the GitHub issue number.

Read the complete issue:

```bash
gh issue view <issue-number> --comments
```

Treat the issue description and acceptance criteria as the implementation specification.

Do not select or implement a different issue.

### 3. Claim the issue

Add a comment:

```bash
gh issue comment <issue-number> \
  --body "Implementation started by Codex."
```

Before commenting, check whether another agent has already claimed the issue. Do not work on an issue that is actively being implemented by another agent.

### 4. Create the feature branch

Determine the default branch:

```bash
DEFAULT_BRANCH="$(gh repo view \
  --json defaultBranchRef \
  --jq '.defaultBranchRef.name')"
```

Fetch it:

```bash
git fetch origin "$DEFAULT_BRANCH"
```

Create a dedicated branch:

```bash
git switch -c "issue-<issue-number>-<short-description>" \
  "origin/$DEFAULT_BRANCH"
```

Do not work directly on the default branch.

### 5. Inspect before editing

Before changing code:

* Read `AGENTS.md`.
* Inspect the relevant architecture and existing patterns.
* Locate the files related to the issue.
* Identify existing tests covering the affected behavior.
* Review recent related commits when useful.
* Form a concise implementation plan.

Avoid unrelated refactors.

### 6. Implement the issue

Implement every stated requirement and acceptance criterion.

Follow these rules:

* Preserve existing architecture and conventions.
* Maintain strict per-user data isolation.
* Do not add unlabeled mock behavior.
* Do not expose secrets or sensitive data.
* Add or update relevant tests.
* Update documentation when behavior or setup changes.
* Do not weaken or delete legitimate tests merely to make checks pass.
* Modify unrelated files only when strictly necessary.

### 7. Verify the implementation

Run the checks relevant to the changed code.

At minimum, use the applicable commands from `AGENTS.md`, including:

```bash
pnpm check
.venv/bin/pytest apps/api
```

Run narrower tests first when helpful, followed by the broader relevant suite.

Also run:

```bash
git diff --check
git status --short
git diff --stat
```

Fix failures caused by the implementation before proceeding.

Do not claim that a check passed unless it was actually run successfully.

### 8. Review and commit

Review the complete diff:

```bash
git diff
git status
```

Stage only files related to the issue:

```bash
git add <related-files>
```

Create a descriptive commit that references the issue:

```bash
git commit -m "<type>(<scope>): <description> (#<issue-number>)"
```

Examples:

```bash
git commit -m "feat(search): add semantic result grouping (#12)"
git commit -m "fix(auth): isolate cached OAuth tokens by user (#18)"
```

### 9. Push the branch

A local commit is not completion.

Run:

```bash
BRANCH="$(git branch --show-current)"

test -n "$BRANCH"
test "$BRANCH" != "$DEFAULT_BRANCH"

git push --set-upstream origin "$BRANCH"
```

Verify the remote branch exists:

```bash
git ls-remote --exit-code --heads origin "$BRANCH"
```

If the push fails:

* Read the exact error.
* Attempt reasonable authentication or upstream fixes.
* Do not push directly to the default branch.
* Do not claim completion.
* Report the unresolved blocker exactly.

### 10. Open the pull request

Prepare a pull request body that includes:

* Summary of the implementation.
* Important technical decisions.
* Tests and checks run.
* Remaining limitations or risks.
* `Closes #<issue-number>`.

Create the pull request non-interactively:

```bash
gh pr create \
  --base "$DEFAULT_BRANCH" \
  --head "$BRANCH" \
  --title "<concise pull request title>" \
  --body "$(cat <<'EOF'
## Summary

- <implemented change>
- <implemented change>

## Verification

- `<command>` — passed
- `<command>` — passed

## Notes

- <remaining risk, limitation, or "None">

Closes #<issue-number>
EOF
)"
```

Use `--draft` when the implementation is incomplete, uncertain, or requires substantial human review.

Do not use an interactive `gh pr create` command.

### 11. Verify and update the issue

Retrieve the pull request URL:

```bash
PR_URL="$(gh pr view "$BRANCH" --json url --jq '.url')"
test -n "$PR_URL"
```

Comment on the issue:

```bash
gh issue comment <issue-number> \
  --body "Implemented in ${PR_URL}. Verification details are included in the pull request."
```

Do not manually close the issue. Allow `Closes #<issue-number>` to close it after merge.

### 12. Final response

Before finishing, run:

```bash
git status --short
git branch --show-current
git log -1 --format='%H %s'
gh pr view "$BRANCH" \
  --json url,state,baseRefName,headRefName
```

Your final response must include:

* Issue number and title.
* Summary of what was implemented.
* Branch name.
* Commit SHA.
* Tests and checks run, with results.
* Pull request URL.
* Any remaining limitations or blockers.

If no pull request URL exists, the task is not complete.

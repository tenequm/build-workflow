---
type: Finding
title: Files carried into worktrees via copy_files must be git-excluded or every agent merge fails
description: Agents commit with git add -A, so copy_files inputs land in their branch and the merge back collides with the parent's untracked originals; the deliverable completes in the worktree and never lands, while task bookkeeping shows phantom failures.
tags: [bernstein, review-pr, git]
status: stable
generated: { by: claude-code/fable-5, at: "2026-09-11T20:55:26Z" }
sources:
  - id: logs
    resource: spawner_merge log lines from three runs on this host, 2026-09-11 - 'Merge failed ... The following untracked working tree files would be overwritten by merge' for .bernstein-pr.diff/.bernstein-pr.md
    title: merge failures
  - id: fix
    resource: /fixtures/review-pr-cases/harness.py
    title: materialise() writes .git/info/exclude
---

# Finding

`worktree_setup.copy_files` copies untracked inputs into every agent worktree
(worktrees cut from a commit cannot see the parent's untracked files). The
agents' own workflow ends with `git add -A`, so those copies get committed to
the agent branch; merging that branch back into the parent then refuses,
because the same files sit untracked at the destination.[^logs]

The failure is quiet and misattributed: the agent's work is complete in its
worktree, bernstein reaps it, marks the task failed, and later retries may or
may not land the deliverable through a resume session. Runs "succeed" with
phantom task failures or fail with the report written but unreachable.

Fix: put every copy_files name in `.git/info/exclude` of the parent checkout
before the run - worktrees share it, `add -A` skips the copies everywhere,
and merges come back clean.[^fix]

[^logs]: merge failures
[^fix]: materialise() writes .git/info/exclude

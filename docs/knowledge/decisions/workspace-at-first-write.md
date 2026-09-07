---
type: Decision
title: Workspace-at-first-write replaces the primary lock
description: A build occupies only its workspace branch from the first artifact write, so other sessions work on main freely; the repo-wide primary lock of 2026-09-03 was dropped for this on 2026-09-04.
tags: [build-pipeline, git, concurrency, worktrees]
status: stable
generated: { by: claude-code/fable-5, at: 2026-09-07T14:42:00Z }
sources:
  - id: primary-lock
    resource: https://github.com/tenequm/build-workflow/commit/0813b9673ab8d24509ceb92154643eb1f25eabc2
    title: "chore: move template check into plan-lint script, add just check (adds the primary lock)"
  - id: first-write
    resource: https://github.com/tenequm/build-workflow/commit/add7263c230bae9662b123226f164dce8945a1c6
    title: "feat(skills): workspace at first artifact write"
  - id: drop-lock
    resource: https://github.com/tenequm/build-workflow/commit/9f857b743c03a1ceb2008f601916585369aa01ed
    title: "docs(build-close): drop the primary lock for workspace-at-first-write"
  - id: retro-session
    resource: operator's pond archive, session 35c0a261, scratchpad workflow-retro-validation.md (not in this repository)
    title: Retro validation of 2026-09-03 holding the incident detail
---

# Decision

From the first artifact write, a build lives entirely on its workspace
branch: sign-off, plan, evidence, and implementation all commit there, the
primary branch is never committed to by the plan, and `/build-close`'s merge
resolves whatever drift the primary accumulated meanwhile. The only shared
write is the primary's `.claude/settings.local.json`, written once at
workspace creation.[^first-write][^drop-lock]

# What it replaced, and why

The original design ran the plan stage in the primary checkout and made
sign-off a commit on the primary branch, which pinned the build to a
specific primary HEAD. On 2026-09-03 another session moved the primary under
an active build and caused a stop-and-verify incident; the same day a
primary-to-workspace resync nearly reverted workspace edits, stopped only by
a failed directory change.[^primary-lock]

The first response was a repo-wide lock - no other session may commit or
push while a build runs - which serialized all work in the repository around
every build.[^primary-lock] The next day the design inverted: instead of
freezing the primary, the workspace branches from wherever the primary is at
first write, sign-off moved onto the workspace branch, and the lock was
deleted.[^first-write][^drop-lock] Corollary: the workspace branch is the
truth after creation - never resync it from the primary.

# Evidence limits

The repository records the incident's effect and date but not its detail;
that lives outside the repo.[^retro-session]

[^primary-lock]: chore: move template check into plan-lint script (adds the primary lock)
[^first-write]: feat(skills): workspace at first artifact write
[^drop-lock]: docs(build-close): drop the primary lock for workspace-at-first-write
[^retro-session]: Retro validation of 2026-09-03 holding the incident detail

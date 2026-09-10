---
type: Finding
title: An executor model below the brief's complexity fails as a clean exit, not an error
description: Codex gpt-5.6-luna repeatedly failed the same executor brief that gpt-5.6-terra and Claude Sonnet 5 completed - it wandered off the brief, wrote its report outside the declared path and exited 0 without committing, which the engine reports as a dead agent and salvages as WIP. The failure signature points at sandboxing or the harness while the cause is capability, so the role_model_policy floor is an operational property of a build, not a cost dial.
tags: [executors, codex, models, role-policy, operations]
status: stable
stale_after: "2027-03-10T00:00:00Z"
generated: { by: claude-code/opus-5, at: "2026-09-10T20:10:00Z" }
sources:
  - id: builds
    resource: Operator builds on the textkit.slugify fixture, 2026-09-10
    title: Seven multi-phase builds plus two single-phase builds carried to build_completed
  - id: probe
    resource: Direct codex exec probe in a Bernstein agent worktree, 2026-09-10
    title: gpt-5.6-luna committed correctly in the same nested-worktree layout when given a one-line instruction
  - id: adapter
    resource: https://github.com/sipyourdrink-ltd/bernstein/blob/0a6bf9f2d/src/bernstein/adapters/codex.py
    title: _worktree_gitdir_roots grants the linked worktree's git dir, the failure this was first mistaken for
---

# Finding

On the same frozen brief, `gpt-5.6-luna` failed every attempt while
`gpt-5.6-terra` and Claude Sonnet 5 delivered.[^builds] The failing agent did
not error: it explored, ran commands the brief never mentioned (`bernstein
status`, `bernstein doctor`), hunted for a formatter the repository does not
have, wrote its report to a path outside the declared one, and exited 0 with
its work uncommitted. The engine reads that as a dead agent, salvages the
worktree as a `[WIP]` commit, and retries.

# Why it reads as an infrastructure fault

Every visible symptom points somewhere else. The agent reports sandbox
rejections (it is writing outside its allowlist), its worktree looks sparse
(it raced the checkout), and its commit never lands (it never ran `git
commit`). The first hypothesis - that Codex could not write the linked
worktree's git metadata - is a real failure mode the engine already fixes with
a writable-root grant,[^adapter] which makes it a convincing explanation. It
was wrong here: a direct probe with the same model, the same nested worktree
and the engine's exact arguments committed without trouble.[^probe] The
difference between the probe and the run was the size of the instruction.

# What follows for a plan

`role_model_policy` is part of a build's correctness, not only its cost. A
model that cannot hold a 6k-character brief with an allowlist, a validation
command and a report contract will burn attempts, salvage partial work into
the integration branch and consume the whole-build retry budget before
anything is delivered. Prefer the strongest model the budget allows for
executor roles, and treat a repeated "agent died, nothing committed" cycle as
a capability signal before investigating the sandbox. The reverse case is
cheap to test: one build against one step is enough to separate the two.

[^builds]: Operator builds on the fixture, 2026-09-10
[^probe]: Direct codex exec probe in an agent worktree
[^adapter]: The engine's writable-root grant for linked worktrees

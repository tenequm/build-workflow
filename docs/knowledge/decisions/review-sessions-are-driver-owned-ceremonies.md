---
type: Decision
title: Review sessions are driver-owned ACP ceremonies, not engine tasks
description: /review-pr runs its reviewers and verifiers as one-shot acpx sessions the driver launches, polls and reaps, because a read-only task that must not commit gets nothing from the engine's worktree, scorer and merge machinery, while the one thing the engine would contribute - a retry when a worker claims completion with no work - is the report-witness law, which the driver implements in ten lines and can then apply per stage.
tags: [review-pr, orchestration, acp, bernstein]
status: stable
generated: { by: claude-code/opus-5, at: "2026-09-11T03:40:00Z" }
sources:
  - id: plan
    resource: ../../plans/2609-11-review-pr.md
    title: /review-pr plan - the phase map that called for one engine run per stage
  - id: boundary
    resource: /decisions/phase-boundary-between-engine-runs.md
    title: Phase ordering lives between engine runs, not inside one
  - id: done-release
    resource: /findings/bernstein-done-releases-before-verification.md
    title: Bernstein releases dependents on worker-reported DONE, before any verification
  - id: witness
    resource: /decisions/completion-signals-name-the-report.md
    title: Every step's completion signal names the report the step must commit
  - id: floor
    resource: /findings/executor-model-capability-floor.md
    title: An executor model below the brief's complexity fails as a clean exit, not an error
  - id: ceremony
    resource: ../../../skills/build-run/scripts/operator_driver/ceremony.py
    title: The detached blind-review ceremony this generalises - staged input, allowlist check, reaping, immutable receipt
  - id: runner
    resource: ../../../skills/review-pr/scripts/review_pr/runner.py
    title: The review-pr session runner, with run_batch's retry and allowlist validation
---

# What was decided

`/review-pr`'s model stages - four review lenses, the claim extractor, one verifier per
surviving finding, the body writer - run as one-shot ACP sessions through `acpx`, each
in its own detached worktree, launched and reaped by the driver as a batch that returns
only once every receipt is written. No Bernstein task server, orchestrator, scorer or
merge queue is involved. The plan that specified this workflow described stage 2 as
"four parallel reviewer tasks" on an engine run;[^plan] this is the deviation, and the
quality mechanisms it specified are all preserved.

# Why

**The engine's machinery is for work that lands commits.** A reviewer reads, greps, and
writes one JSON report; it must never commit, never merge, and never touch a second
file. Worktree leasing, the scorer's owned-file diffing, gate repair, the merge queue
and dead-agent salvage all exist to get authored code safely onto a branch. Pointed at
a read-only task they add failure modes and buy nothing: the report would have to be
committed and merged to be collected at all.

**The one thing worth keeping is cheap to keep.** The engine's real contribution here
would be a retry when an executor exits 0 having produced nothing - the capability-floor
failure shape.[^floor] That is the report-witness law,[^witness] and driver-side it is a
file check plus a literal check: a task whose declared report is absent, or whose report
does not contain the literal its brief asked for, is a failed attempt, retried once on a
fresh session, then recorded as failed with its evidence.[^runner] Because the driver
owns it, the same rule covers every stage rather than only tasks the engine happens to
verify, and a plan-post helper that drops `completion_signals` cannot lose it.

**It keeps the stage boundary sound by construction.** The engine releases a dependent
the moment a worker claims DONE, before any verification,[^done-release] which is why
phase ordering already lives between engine runs rather than inside one.[^boundary]
Verification must not begin until production is complete and read, so stage 3 could
never have been an in-DAG dependent of stage 2 anyway. With each stage a separate
driver-owned batch, that ordering is a property of the code path rather than of a
dependency edge that does not mean what it looks like.

**The mechanism already existed and was already proven.** The blind-judge ceremony does
exactly this shape - stage an exact input, run one bounded ACP session, validate that
the tree changed only in the declared paths, reap survivors, archive an immutable
receipt with the measured USD cost.[^ceremony] `/review-pr` generalises it to a parallel
batch of them. That also keeps the skill installable on its own: it vendors five
primitive modules rather than a whole build driver.

# What this costs

Dispatch, retries and concurrency are now this workflow's code rather than the engine's,
so they are its bugs too - which is why the batch is covered by tests that run the real
`acpx` transport against a recording agent, including the missing report, the report
that does not witness itself, a session that writes outside its allowlist, an
over-budget session and a concurrent batch. An unmetered transport reports no cost, so
its ceremony settles at its full reservation rather than reading an absent number as
zero, exactly as the judge ceremony already does.

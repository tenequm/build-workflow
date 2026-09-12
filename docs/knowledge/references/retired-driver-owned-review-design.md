---
type: Reference
title: The driver-owned /review-pr design, retired 2026-09-11
description: The record of what /review-pr was before it moved onto the stock bernstein orchestrator - a custom Python driver running five review lenses, per-finding blinded verification and synthesis as one-shot ACP sessions it launched and reaped itself, with per-run pond capture - and the corpus score it reached; the code is in git history, at the commit before the purge.
tags: [review-pr, history, artifact-record]
status: stable
generated: { by: claude-code/opus-5, at: "2026-09-11T19:25:51Z" }
sources:
  - id: ledger
    resource: ../../review-ledger/evals.jsonl
    title: The eval ledger - every corpus run of the retired pipeline, rows 1-10
  - id: plan
    resource: ../../plans/2609-11-review-v3.md
    title: The plan that retired it, including the purge list
  - id: git
    resource: "Git history of this repository at 929787c, the commit before the purge commit: skills/review-pr/scripts/ (6,923 lines), skills/review-pr/templates/stages*.yaml, fixtures/review-pr/, bernstein_operator/tests/test_review_*.py"
    title: Where the code is
---

# What it was

/review-pr ran its own orchestrator: a Python driver in `skills/review-pr/scripts/`
that checked out the pull request, ran mechanical house rules and a base-pinned
validation command in a network-less sandbox, then spawned every model stage itself as
a one-shot acpx session in a detached worktree - five review lenses in parallel
(cleanliness, design, efficiency, gating, claim-vs-implementation), one blinded
verifier per finding under a fan-out cap, and a synthesis stage that produced the
review body and verdict table. Findings carried executable rubrics the driver ran
before any verifier spent, gated by a fail-on-head/pass-on-base control leg; briefs
came from vendored templates and routing from a `stages*.yaml` dialect per lane. Each
run provisioned its own pond store with a pinned binary, captured every session
transcript into it, and priced the run after the fact as a labeled floor. A recording
ACP agent in `fixtures/review-pr/` exercised the whole transport for no provider
spend.

# What it scored

Against the frozen 14-case corpus in `fixtures/review-pr-cases/`, on the opencode Zen
free lane (`stages-fast.yaml`):[^ledger]

| run | date (UTC) | recovered | missed | misfiled |
|---|---|---|---|---|
| best executed | 2026-09-11 14:22 | 13 / 14 | 1 | 0 |
| best scored | 2026-09-11 14:24 | 14 / 14 | 0 | 0 |
| last | 2026-09-11 16:49 | 13 / 14 | 1 | 0 |

The 14/14 row is a rescore of the 14:22 workspaces under a widened mention scan, with
no sessions re-run; 13/14 is the honest ceiling the pipeline reached under execution.
Ledger rows measuring a single case are partial runs and are not comparable. Path-A
rows open a new comparability regime and are not comparable to any of these.[^plan]

# Where the code is

In git history, at the commit before the purge commit.[^git] Nothing was kept in the
tree: the driver package, its stage templates, its briefs, the recording-agent fixture
and its 4,270 lines of tests were deleted together.

[^ledger]: The eval ledger - every corpus run of the retired pipeline, rows 1-10
[^plan]: The plan that retired it, including the purge list
[^git]: Where the code is

---
type: Finding
title: A resource outage becomes a permanent run failure, and a shadow dependency spreads it
description: Bernstein turns a transient host shortage into an unrecoverable run - a task that cannot spawn burns its respawn budget, then its retry budget, then quarantines, and quarantine survives the resource returning. Anything listed in that task's dependents is blocked forever, so a dependency on an agent whose output is contractually ignored can end a run that was otherwise complete.
tags: [review-pr, bernstein, orchestration, reliability]
status: stable
generated: { by: claude-code/opus-5, at: "2026-09-14T17:05:00Z" }
sources:
  - id: run
    resource: /docs/evals/2609-14-pond-237/run-1-aborted/failure-lines.log
    title: pond#237 run 1, the failure lines of the orchestrator debug log, 2026-09-14
  - id: graph
    resource: /docs/evals/2609-14-pond-237/run-1-aborted/task-graph.json
    title: pond#237 task graph at the moment run 1 died
  - id: goal
    resource: /skills/review-pr/templates/review-goal.md
    title: The review goal text, whose report section ignores every shadow- file
  - id: manager
    resource: /skills/review-pr/templates/bernstein-templates/roles/manager/system_prompt.md
    title: The manager role template that sets depends_on
---

# Finding

**A resource shortage does not degrade a bernstein run, it ends one permanently.**
Below its floor the spawner refuses to start an agent at all.[^run] A task that
cannot spawn is not retried against the shortage later: it exhausts a respawn
budget (2 within 300s), then a retry budget, and lands in quarantine at
`fail_count=3, action=skip`. Quarantine is terminal and cross-run. Returning the
resource afterwards recovers nothing - measured directly, because the resource
was returned twelve minutes before the run was declared dead and every
quarantined task stayed quarantined.[^run]

This inverts the instinct that a transient shortage costs only time. The window
in which it must be noticed is the length of two respawns, roughly five minutes.
Outside that window the cost is the whole run.

## The failure is invisible where anyone would look

Both limits are written only to `.sdd/runtime/orchestrator-debug.log`. The run
log showed a clean banner, the full adapter list, and nothing else, for the
entire thirteen minutes the run spent dying.[^run] Any health check reading the
run log reports a healthy run. The task graph is the honest surface: statuses
`failed`, `blocked_by_failed_dep`, and a `failed` count that climbs.[^graph]

## A dependency on an ignored artifact is still a dependency

The pond#237 lane runs five numbered lenses plus two `-shadow` lenses, a
second reader kept for comparison. The goal text instructs the report writer to
ignore every file whose name begins with `shadow-`; a shadow finding cannot
enter the report by construction.[^goal] The manager template nonetheless said
the report "depends on every lens file", and the manager duly listed both
shadows in `depends_on`.[^manager]

So when the shortage hit, the report task sat at `blocked_by_failed_dep` behind
`lens-5-cleanliness-shadow` - an agent whose output it was forbidden to
read.[^graph] Five of seven lenses had completed successfully. A degraded report
was available and unreachable.

**The general lesson: a dependency edge must be justified by a consumed artifact,
not by a role's membership in a group.** "Depends on all of them" is a plausible
sentence and a wrong graph whenever some of "them" produce something the consumer
discards. The blast radius of a failure is the transitive closure of `depends_on`,
so every edge that carries no data is pure imported risk.

## What closes it

Prose in a skill cannot close either half, because both failures happen before
any model reads anything. Both are now checks:

- The invocation refuses to start when **either** the working filesystem or `/tmp`
  is below a floor. Both are needed, and the second is the one that bit: a
  sandboxed worker is handed a hardcoded `TMPDIR=/tmp` and never sees an exported
  one, so a lens that copies the repository into its own `mktemp -d` and builds
  there spends `/tmp` whatever the parent set. Exporting `TMPDIR` still moves the
  parent's own scratch and is worth doing; it is not a substitute for checking the
  filesystem the workers are pinned to.

  The general shape: **an environment variable that configures a child process is
  a control only where the child actually inherits it.** A sandbox boundary that
  rewrites the environment turns such a setting into a comforting no-op, and what
  catches it is measuring where files landed, not confirming the export was set.
- The corpus harness refuses the lane on the same floor, scaled by concurrency,
  and gained a `disk_exhausted` detector beside `lane_down` so a starved run
  scores ERROR rather than MISSED. Scoring it MISSED would file a host outage as
  a model failure in the ledger, which is the one thing the ledger must not say.
- The manager template now names the five numbered lens tasks as the report's
  only dependencies and forbids a `-shadow` task from ever appearing there.

See also [a hung model lane fails as a dead agent](a-hung-model-lane-fails-as-a-dead-agent.md),
which is the same shape one layer up: an infrastructure failure arriving at the
grader disguised as a model result.

[^run]: pond#237 orchestrator debug log, 2026-09-14. `Disk space critical: 0.3 GB free (need >= 1.0 GB)`; `Session 'batch:815236c89df9' parked after exhausting respawn budget (2 respawn(s) in 300s window)`; `Task 'Lens 5: cleanliness' exhausted 2 retries -- recorded cross-run failure in quarantine`; `Skipping quarantined task ... fail_count=3, action=skip` still firing after the resource was returned.
[^graph]: pond#237 task graph: `manager`, `lens-2-side-effects`, `lens-3-design`, `lens-4-efficiency`, `lens-4-efficiency-shadow` all `done`; six `failed` entries across `lens-5-cleanliness` and its shadow; `report-writer` at `blocked_by_failed_dep`.
[^goal]: review-goal.md, report section: "ignore every file whose name begins with `shadow-`. Those are a second reader kept for comparison afterwards; a finding that appears only in a `shadow-` file does not enter the report."
[^manager]: manager/system_prompt.md, task dependencies section, before this change: "the report task reads every lens file, so it depends on all of them".

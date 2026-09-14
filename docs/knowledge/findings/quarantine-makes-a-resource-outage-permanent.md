---
type: Finding
title: A resource outage becomes a permanent run failure, and unnecessary dependencies spread it
description: Bernstein turns a transient host shortage into an unrecoverable run - a task that cannot spawn burns its respawn budget, then its retry budget, then quarantines, and quarantine survives the resource returning. The pond#237 run showed how an in-band comparison task amplified that failure through a needless dependency; model comparisons now run out-of-band and never enter the production review graph.
tags: [review-pr, bernstein, orchestration, reliability]
status: stable
generated: { by: codex-cli/gpt-5, at: "2026-09-14T20:45:00Z" }
sources:
  - id: run
    resource: /docs/evals/2609-14-pond-237/run-1-aborted/failure-lines.log
    title: pond#237 run 1, the failure lines of the orchestrator debug log, 2026-09-14
  - id: graph
    resource: /docs/evals/2609-14-pond-237/run-1-aborted/task-graph.json
    title: pond#237 task graph at the moment run 1 died
  - id: historical
    resource: "Git tree at 3e4a23a: review-goal.md declared two shadow roles whose files the report ignored, while manager/system_prompt.md excluded those roles from the report dependency list after the pond#237 failure"
    title: The historical in-band shadow graph and its first dependency fix
  - id: boundary
    resource: "Git commits c5a0ae1 and 711f340: all shadow roles, routes, prompts and instructions were removed from /review-pr; the ensuing four-case run recovered 4/4 and each task graph contained only manager, five production lenses and report writer with five report dependencies"
    title: The out-of-band comparison boundary and its corpus proof
  - id: tmpdir
    resource: /docs/knowledge/findings/worker-scratch-follows-tmpdir.md
    title: The measurement that corrected this concept's TMPDIR claim, 2026-09-14
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

## Historical failure: a dependency on an ignored artifact

The pond#237 lane ran five numbered lenses plus two `-shadow` lenses, a
second reader kept for comparison. The goal text instructed the report writer to
ignore every file whose name began with `shadow-`; a shadow finding could not
enter the report by construction. The manager nonetheless listed both shadows in
`depends_on`.[^historical]

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

- The invocation refuses to start below its disk floor. Worker scratch follows
  `TMPDIR`, so the harness names it beside the workspace and checks both locations;
  the measurement and the correction to the earlier hardcoded-`/tmp` explanation
  live in [worker scratch follows TMPDIR](worker-scratch-follows-tmpdir.md).[^tmpdir]
- The corpus harness refuses the lane on the same floor, scaled by concurrency,
  and gained a `disk_exhausted` detector beside `lane_down` so a starved run
  scores ERROR rather than MISSED. Scoring it MISSED would file a host outage as
  a model failure in the ledger, which is the one thing the ledger must not say.
- The production workflow no longer has a shadow task to fail or depend on. Model
  comparisons are separate Pond experiments over the same lens text, never roles,
  routes, prompts, findings files or report inputs inside `/review-pr`. The four-case
  proof inspected each runtime graph as well as its verdicts.[^boundary]

See also [a hung model lane fails as a dead agent](a-hung-model-lane-fails-as-a-dead-agent.md),
which is the same shape one layer up: an infrastructure failure arriving at the
grader disguised as a model result.

[^run]: pond#237 orchestrator debug log, 2026-09-14. `Disk space critical: 0.3 GB free (need >= 1.0 GB)`; `Session 'batch:815236c89df9' parked after exhausting respawn budget (2 respawn(s) in 300s window)`; `Task 'Lens 5: cleanliness' exhausted 2 retries -- recorded cross-run failure in quarantine`; `Skipping quarantined task ... fail_count=3, action=skip` still firing after the resource was returned.
[^graph]: pond#237 task graph: `manager`, `lens-2-side-effects`, `lens-3-design`, `lens-4-efficiency`, `lens-4-efficiency-shadow` all `done`; six `failed` entries across `lens-5-cleanliness` and its shadow; `report-writer` at `blocked_by_failed_dep`.
[^historical]: the historical in-band shadow graph and its first dependency fix
[^boundary]: the out-of-band comparison boundary and its corpus proof
[^tmpdir]: the corrected TMPDIR measurement

---
type: Decision
title: Phase ordering lives between engine runs, not inside one
description: A build executes one Bernstein run per phase and the driver owns the boundary - teardown, delivery predicate, driver-side blind judge, pinned fix mini-runs - because the engine's optimistic DONE-release makes every in-DAG barrier unsound; settled 2026-09-08 after two in-DAG designs were falsified.
tags: [build-pipeline, bernstein, orchestration, judge-routing]
status: stable
generated: { by: codex/gpt-6, at: "2026-09-08T11:24:53Z" }
sources:
  - id: plan
    resource: ../../plans/2609-08-bernstein-operator.md
    title: bernstein_operator plan, fourth revision - full contracts, acceptance evidence, upstream enablers
  - id: done-release
    resource: /findings/bernstein-done-releases-before-verification.md
    title: Bernstein releases dependents on worker-reported DONE, before any verification
  - id: unwired
    resource: /findings/declared-but-unwired-engine-surfaces.md
    title: A documented Bernstein surface is not a wired one
  - id: why-det
    resource: https://github.com/sipyourdrink-ltd/bernstein/blob/0a6bf9f2d/docs/architecture/WHY_DETERMINISTIC.md
    title: Upstream assigns mid-run task creation to the operator ("the orchestrator will not infer the need")
  - id: reviews
    resource: operator's session scratch, adversarial gpt-6-astra review rounds 1-4 (not in this repository)
    title: Four-round adversarial settlement, final verdict approve-with-nits, 2026-09-08
  - id: shutdown
    resource: https://github.com/sipyourdrink-ltd/bernstein/blob/0a6bf9f2d/src/bernstein/core/orchestration/orchestrator.py
    title: Shutdown records run_completed before run_quiescence; quiescence failures are recorded without blocking closure (~3405-3465)
  - id: watchdog
    resource: https://github.com/sipyourdrink-ltd/bernstein/blob/0a6bf9f2d/src/bernstein/core/orchestration/bootstrap.py
    title: Supervisor stand-down checks only the last event in its owner's run journal (~1035-1089)
---

# Decision

A build runs **one Bernstein engine run per phase**, containing only that
phase's executor steps. The driver (build-run) owns the phase boundary: it
tears the run's infrastructure down after the quiescent stop, proves
delivery per frozen step (attempt -> scorer PASS -> commit -> ancestry in a
pinned tip), stages and runs the **blind phase judge as a driver-side
ceremony** - not a task, not a gate plugin - and reacts to the archived
verdict by posting the pinned fix as its own mini-run or releasing the next
phase. Judge-shaped code leaves the engine process entirely; the installed
package shrinks to a single scorer gate plugin. Full contracts, template
settings, and acceptance evidence live in the plan.[^plan]

# What it replaced, and why twice

Two in-DAG designs were considered and falsified in one day:

1. **Hook-posted fix task** (draft 1): a `post_merge` lifecycle hook script
   posting the fix. Falsified - the hook bus fires nothing on the plan-run
   path.[^unwired]
2. **Native blocking + `retry_of` revival** (draft 2): the judge gate exits
   1, the failed-dependency cascade strands the next phase, a driver-posted
   retry task revives it. Falsified by an executed store probe - dependents
   release on worker-reported DONE before the judge's gate ever evaluates
   the verdict, so the strand never reliably forms; additionally `retry_of`
   is not recursive, janitor reopens reuse the same task id without the fix
   edge, and `POST /tasks` is not idempotent.[^done-release]

The surviving insight is that the engine itself locates conditional,
verdict-driven work with the operator[^why-det]: the driver posting the
next phase only after acceptance is Bernstein's own model, not a bolt-on.
An adversarial review accepted the architecture in round 3 and approved the
written contracts in round 4.[^reviews]

# Boundary conditions that make it sound

The stop alone is not the boundary - the driver's contract is. In the
audited source, shutdown appends `run_quiescence` after `run_completed`,
while watchdog stand-down requires `run_completed` to be the **last**
journal event. A complete shutdown therefore defeats that particular
stand-down check. Moreover, the presence of `run_quiescence` is not proof
of quiescence: a failed check records `verified: false`, and surviving
processes do not prevent native closure.[^shutdown][^watchdog]

The task server and watchdog outlive the scheduler, and ingress paths (workflow importer,
backlog sync, the default-ON test follow-up) can add tasks the driver never
posted. The plan's launch transaction, teardown contract, and delivery
predicate exist to close exactly these gaps; skipping any of them re-opens
a falsified design.[^plan]

Those upstream defects can be fixed without invalidating the decision:
scheduler closure still does not establish delivery, review acceptance, or
exclusive ownership of the integration branch. The driver owns those
predicates independently of which native shutdown helpers are available.[^plan]

[^plan]: [bernstein_operator plan, fourth revision - full contracts, acceptance evidence, upstream enablers](../../plans/2609-08-bernstein-operator.md)
[^done-release]: [Bernstein releases dependents on worker-reported DONE, before any verification](/findings/bernstein-done-releases-before-verification.md)
[^unwired]: [A documented Bernstein surface is not a wired one](/findings/declared-but-unwired-engine-surfaces.md)
[^why-det]: [Upstream assigns mid-run task creation to the operator ("the orchestrator will not infer the need")](https://github.com/sipyourdrink-ltd/bernstein/blob/0a6bf9f2d/docs/architecture/WHY_DETERMINISTIC.md)
[^reviews]: Four-round adversarial settlement, final verdict approve-with-nits, 2026-09-08. Source: operator's session scratch, adversarial gpt-6-astra review rounds 1-4 (not in this repository).
[^shutdown]: [Shutdown records run_completed before run_quiescence; quiescence failures are recorded without blocking closure (~3405-3465)](https://github.com/sipyourdrink-ltd/bernstein/blob/0a6bf9f2d/src/bernstein/core/orchestration/orchestrator.py)
[^watchdog]: [Supervisor stand-down checks only the last event in its owner's run journal (~1035-1089)](https://github.com/sipyourdrink-ltd/bernstein/blob/0a6bf9f2d/src/bernstein/core/orchestration/bootstrap.py)

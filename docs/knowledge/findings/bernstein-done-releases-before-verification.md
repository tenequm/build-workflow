---
type: Finding
title: Bernstein releases dependents on worker-reported DONE, before any verification
description: The engine's dependency model is optimistic - a task's dependents unblock and can spawn the moment the worker claims completion, before gates, janitor, or merge run - so no in-DAG dependency edge can enforce verified-before-start ordering.
tags: [bernstein, orchestration, scheduling, verification]
status: stable
generated: { by: claude-code/fable-5, at: "2026-09-08T11:25:00Z" }
sources:
  - id: complete
    resource: https://github.com/sipyourdrink-ltd/bernstein/blob/0a6bf9f2d/src/bernstein/core/tasks/task_store_core.py
    title: TaskStore.complete transitions to DONE and immediately revives/unblocks dependents (lines ~2368-2385)
  - id: tick
    resource: https://github.com/sipyourdrink-ltd/bernstein/blob/0a6bf9f2d/src/bernstein/core/orchestration/orchestrator.py
    title: Readiness accepts DONE (~1743-1768); claim_and_spawn_batches (~2099) runs before process_completed_tasks (~2108)
  - id: cache
    resource: https://github.com/sipyourdrink-ltd/bernstein/blob/0a6bf9f2d/src/bernstein/core/tasks/task_lifecycle.py
    title: Response-cache hit completes a task with no agent spawn and no gate (~2420-2440); verified flag computed before merge success (~3819)
  - id: upstream-test
    resource: https://github.com/sipyourdrink-ltd/bernstein/blob/0a6bf9f2d/tests/unit/test_retry_unblocks_dependents.py
    title: Upstream's own test encodes that store.complete (not close) releases a retry's successor
  - id: probe
    resource: operator's session scratch, adversarial gpt-6-astra review round 2 with an executed TaskStore probe (not in this repository)
    title: Second adversarial review of the bernstein_operator plan, 2026-09-08
---

# Finding

`TaskStore.complete()` transitions a task to DONE on the worker's own claim
and, in the same call, revives blocked dependents and runs the unblock
cascade.[^complete] Orchestrator readiness treats DONE as satisfying
dependency edges, and each tick spawns ready dependents *before* it
verifies completions - gates, janitor, and merge all run after the release
window opens.[^tick] Upstream's own unit test asserts this ordering as the
intended contract.[^upstream-test] An executed probe against the real store
confirmed it end to end: completing a task made its dependent claimable
with no gate having run.[^probe]

A second unverified-completion path compounds it: a semantic response-cache
hit (exact or fuzzy on role/title/description) completes a single-task
batch with **no agent spawn and no gate execution at all**, and the entry's
`verified` flag is computed before merge success is known.[^cache] There is
no disable switch at this commit.

# Consequence

Gates in this engine are **compensating controls, not barriers**: a failed
verification claws work back after the fact, but cannot prevent a dependent
from starting on an unverified base. Any workflow needing strict
verified-and-merged-before-start ordering must keep the downstream work
*out of the task server entirely* until the upstream work is proven - a
dependency edge, a blocked status, or retry lineage cannot provide it. This
finding falsified an entire revision of the bernstein_operator design (see
[the phase-boundary decision](/decisions/phase-boundary-between-engine-runs.md))
and is the single most load-bearing fact about the engine for this
workflow.

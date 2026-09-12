---
type: Finding
title: An open task the spawner will never claim wedges a bernstein run forever
description: The orchestrator's only self-stop is gated on the RAW open-task count being zero, while the tick line prints a dependency-filtered count - so any task left in `open` that the spawner refuses to claim makes the run tick at full cadence forever with no exit. Three of four eval cases wedged this way on one night, by two producers - a title-keyed quarantine skip that never fails the task, and a strand cascade blind to the retry lineage its unblock counterpart folds in. The gate was itself added as a stall fix, in the same pull request that shipped its compensating detector without a caller.
tags: [bernstein, orchestration, quiescence, review-pr, eval]
status: stable
stale_after: "2027-03-11T00:00:00Z"
generated: { by: claude-code/opus-5, at: "2026-09-11T22:27:45Z" }
sources:
  - id: gate
    resource: bernstein 3.19.1 as installed, core/orchestration/orchestrator.py:2365-2366
    title: "`_raw_open = len(tasks_by_status.get(\"open\", []))` and the `_raw_open == 0` conjunct on the 8b quiescence gate"
  - id: printed
    resource: bernstein 3.19.1 as installed, core/orchestration/orchestrator.py:1765-1772, 6304-6307
    title: result.open_tasks is the dependency-filtered and backoff-filtered subset that the tick line prints as `open=`
  - id: skip
    resource: bernstein 3.19.1 as installed, core/tasks/task_lifecycle.py:2514-2535
    title: claim_and_spawn_batches logs "Skipping quarantined task" and continues, with no fail_task
  - id: title
    resource: bernstein 3.19.1 as installed, core/security/quarantine.py:26,44,139-142
    title: quarantine entries are keyed on task title, threshold 3, 7-day expiry
  - id: reblock
    resource: bernstein 3.19.1 as installed, core/tasks/task_store_core.py:1280-1308
    title: "_cascade_failed_dependency walks `frontier.intersection(candidate.depends_on)` - literal ids only"
  - id: guard
    resource: bernstein 3.19.1 as installed, core/tasks/unreachable.py:95-115 (blocking_dependency / is_task_succeeded_or_retrying) with the retry-before-fail ordering at core/tasks/task_lifecycle.py - POST /tasks 201 precedes POST /tasks/<id>/fail
    title: a live retry suppresses the blocker at the moment the original is failed
  - id: unblock
    resource: bernstein 3.19.1 as installed, core/tasks/task_store_core.py:1387-1412
    title: _cascade_unblock_dependency folds original_task_id and retry_of into solved_blocker_ids
  - id: warnonly
    resource: bernstein 3.19.1 as installed, core/orchestration/orchestrator.py:1857-1863
    title: DependencyValidator.stuck_deps only logs "task remains blocked"; no transition follows
  - id: backstop
    resource: bernstein 3.19.1 as installed, core/orchestration/run_stall.py:64-70, orchestrator.py:2514
    title: "the zero-terminal backstop is called from inside the `_raw_open == 0` block and documents open_tasks > 0 as out of scope"
  - id: dead
    resource: bernstein 3.19.1 as installed, run_stall.py:347 (evaluate_progress_stall) and orchestrator.py:454-455 - the only three matches in the tree
    title: the wedged-claim progress-stall detector has no caller
  - id: measured
    resource: "review-pr eval run of 2026-09-11 21:07Z, quality lane, preserved at /tmp/review-eval-20260911T210735Z: floor/case-02 (open=0 agents=0 for 50 min), floor/case-03 (open=17, 12954 skip lines), floor/case-05 (open=3, 1038 skip lines)"
    title: three of four cases wedged, two shapes
  - id: upstream
    resource: https://github.com/sipyourdrink-ltd/bernstein/pull/3638
    title: "PR #3638 fixed only the quarantine log spam; no upstream issue describes the stall itself"
  - id: provenance
    resource: https://github.com/sipyourdrink-ltd/bernstein/pull/4460
    title: "PR #4460 (commit 9c82a0cd6, first release v3.18.0) added the `_raw_open == 0` conjunct and, in the same change, the unwired evaluate_progress_stall"
  - id: issue4453
    resource: https://github.com/sipyourdrink-ltd/bernstein/issues/4453
    title: "issue #4453, closed by that PR, whose acceptance criterion reads \"agents == 0 with open+claimed > 0 must never be a stable state\""
  - id: mainline
    resource: "upstream main at ebad8f5b3 (2026-09-11T16:25:23Z, version 3.19.2) compared file by file against the installed tree"
    title: "task_lifecycle.py, quarantine.py, task_store_core.py, run_stall.py and unreachable.py are byte-identical; orchestrator.py differs only by two local patches elsewhere in the file, and its gate line matches character for character"
---

# Finding

Bernstein's orchestrator has exactly one clean exit: the step-8b quiescence
block, which the tick loop enters only when

```python
result.open_tasks == result.active_agents == 0 and _raw_open == 0
```

holds.[^gate] The run summary, the settle window, the self-stop and the
zero-terminal backstop all live inside that block, so a single task sitting in
status `open` disables every one of them at once.[^backstop]

The operator cannot see this from the tick line. The `open=` it prints is
`result.open_tasks`, which is already filtered by dependency readiness and
retry backoff; the gate reads the raw `open` bucket.[^printed] A run can
therefore print `open=0 agents=0` on every tick for an hour while the gate
stays shut, which is precisely how the failure hides.

Nothing rescues the state. `run_stall.py` is the designed backstop, but it is
called from inside the same `_raw_open == 0` block and its own docstring puts
`open_tasks > 0` out of scope.[^backstop] Its sibling for the wedged-claim
shape, `evaluate_progress_stall`, was written and never wired: the function and
the two state fields that would feed it are the only three matches in the
installed tree.[^dead]

# The two producers measured

**Quarantine skip.** A task title that fails three times is recorded in
`.sdd/runtime/quarantine.json`, keyed on the **title**, not the id.[^title]
The spawner then logs `Skipping quarantined task <id>` and `continue`s the
whole batch, with no `fail_task` and no status change - the sibling
permanent-skip path a few lines earlier does fail its task first.[^skip]
Because the key is the title, every later task the manager creates with that
same title is born already quarantined. Two cases ended this way, one at
`open=3` and one at `open=17`, emitting the skip line every poll interval
forever.[^measured]

**A retried dependency never strands its dependents.** When a dependency ends
unsuccessfully the store is supposed to move its dependents to
`BLOCKED_BY_FAILED_DEP`. Two mechanics conspire so that it never happens to a
dependency that was retried even once:

- The retry task is created **before** the original is failed, so at the moment
  of the fail, `blocking_dependency` sees a live retry and
  `is_task_succeeded_or_retrying` suppresses the blocker.[^guard]
- The last member of a retry chain carries a **new** id that appears in nobody's
  `depends_on`, and `_cascade_failed_dependency` selects candidates by
  `frontier.intersection(candidate.depends_on)` on literal ids - so the terminal
  failure never reaches the dependent at all.[^reblock]

The reverse direction has no such gap: `_cascade_unblock_dependency` folds
`original_task_id` and `retry_of` into the ids it clears, so a retry's *success*
does release a dependent naming the original.[^unblock] Release is
lineage-aware; strand is not.

The result is a dependent parked in `open`, never stranded, never claimable, on
which the engine's only comment is the dependency validator writing
`Task X depends on Y which is failed - task remains blocked` on every
tick.[^warnonly] That was the third case: a synthesis task whose five lens
dependencies had all been retried and three of whose lineages ended failed. The
string `blocked_by_failed_dep` appears nowhere in that run's logs.[^measured]

# Where the gate came from

The `_raw_open == 0` conjunct is not original. It was added by PR #4460,
first released in v3.18.0, as the fix for issue #4453 - and #4453's acceptance
criterion is the exact state the conjunct now makes permanent: *"agents == 0
with open+claimed > 0 must never be a stable state."*[^provenance][^issue4453]
The same pull request shipped `evaluate_progress_stall`, the detector that
would have caught it, without a caller.[^dead]

So this is not an unhandled edge: it is a stall-prevention fix that tightened
the exit condition and left its own compensating detector disconnected. That
matters for how much to expect of the engine - the operator-side detector below
is not a stopgap awaiting an upstream fix, it is the only thing watching.

# The shape to detect, and why it is not a model failure

Both producers reduce to one operator-visible law: **a bernstein run that is
making no progress will not stop on its own, and the tick line understates how
much is left open.** A harness that treats a timed-out case as a model result
records a false negative for an engine wedge. The distinguishing signal is that
`agents=`, `spawned=`, `reaped=` and `verified=` are all zero on every tick for
longer than any agent is allowed to live, whatever `open=` says.

Neither producer is fixed upstream. Every code path cited above is unchanged in
upstream main at `ebad8f5b3` (version 3.19.2): `task_lifecycle.py`,
`quarantine.py`, `task_store_core.py`, `run_stall.py` and `unreachable.py` are
byte-identical to the installed build, and the gate line in `orchestrator.py`
matches character for character. An engine upgrade removes none of
this.[^mainline] No upstream issue
describes either producer either; the one quarantine PR in this area fixed the
log spam and left the stall.[^upstream] The related quiescence stall
that this project already records -
[a merged task archived to CLOSED](/findings/merged-tasks-close-and-stall-quiescence.md) -
is a different gate on the same block and was not the cause here.

[^gate]: the `_raw_open == 0` conjunct on the only self-stop
[^printed]: `open=` is the filtered count, the gate reads the raw one
[^skip]: the quarantine skip never fails the task
[^title]: quarantine is keyed on task title
[^reblock]: the re-block cascade matches literal ids
[^unblock]: the unblock cascade folds retry lineage
[^guard]: a live retry suppresses the blocker at fail time
[^warnonly]: stuck dependencies are logged, never transitioned
[^backstop]: the backstop lives inside the gate it would rescue
[^dead]: the wedged-claim detector has no caller
[^measured]: three of four eval cases wedged, 2026-09-11
[^upstream]: upstream fixed the log spam, not the stall
[^provenance]: the gate was added by PR #4460, released in v3.18.0
[^issue4453]: the issue it closed forbids exactly the state it creates
[^mainline]: every cited code path is unchanged on upstream main

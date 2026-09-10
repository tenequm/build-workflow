---
type: Finding
title: A merged task is archived to CLOSED, a status the quiescence self-stop does not count
description: The orchestrator self-stops only when a refetch shows a done or failed task, but that refetch omits the CLOSED status a verified, merged task is archived to - so a run whose every task merged idles forever and never journals run_completed/run_quiescence, which is exactly the phase boundary the operator waits for. Recorded executors reach the quiescent tick while still DONE, so no recording finds it.
tags: [bernstein, orchestration, quiescence, phase-boundary, acceptance]
status: stable
stale_after: "2027-03-10T00:00:00Z"
generated: { by: claude-code/opus-5, at: "2026-09-10T17:05:00Z" }
sources:
  - id: close
    resource: https://github.com/sipyourdrink-ltd/bernstein/blob/0a6bf9f2d/src/bernstein/core/tasks/task_store_core.py
    title: "transition_task(task, TaskStatus.CLOSED, ...) - 'verified and closed' (line ~2409)"
  - id: selfstop
    resource: https://github.com/sipyourdrink-ltd/bernstein/blob/0a6bf9f2d/src/bernstein/core/orchestration/orchestrator.py
    title: _had_any_terminal_task reads only done/failed before the settle-window self-stop (~2490)
  - id: fetch
    resource: https://github.com/sipyourdrink-ltd/bernstein/blob/0a6bf9f2d/src/bernstein/core/orchestration/tick_pipeline.py
    title: 'fetch_all_tasks default statuses are ["open", "claimed", "done", "failed"] (~200)'
  - id: deps
    resource: https://github.com/sipyourdrink-ltd/bernstein/blob/0a6bf9f2d/src/bernstein/core/orchestration/orchestrator.py
    title: The same module already counts closed tasks as terminal for dependency release (~1763)
  - id: measured
    resource: The first real operator build (textkit.slugify fixture), 2026-09-10
    title: One merged task, 22 quiescent ticks logging "done 0->0, failed 0->0", no self-stop
---

# Finding

When a task's work is verified and merged, the store does not leave it `DONE`:
it soft-archives it to `CLOSED`.[^close] The orchestrator's end-of-run
self-stop asks whether any task has reached a terminal state before it will
confirm quiescence, and answers with `done or failed` from a refetch whose
default status list does not include `closed`.[^selfstop][^fetch] A run whose
every task merged therefore reports `open=0 agents=0` forever, logs
`8b quiescence detected ... (done 0->0, failed 0->0)` on every tick, and never
executes the self-stop that writes `run_completed` and `run_quiescence`.

That is fatal for this workflow rather than merely untidy: the phase boundary
is defined by exactly those two journal events plus an identified scheduler
exit, so the driver polls until its whole-build wall clock expires and parks a
build whose work actually succeeded.

# Why the acceptance suite could not see it

The recording-executor acceptance run posts its completion and exits
immediately, so its quiescent tick lands while the task is still `DONE` and the
self-stop fires. A real executor's merge completes earlier relative to the tick
loop, so the task is already `CLOSED` when quiescence is first detected. The
difference is timing, not shape, which is why 85 passing tests over real native
servers, real gates and a real merge never exercised the failing ordering.
It took the first build with paid executors to produce it, on the first
try.[^measured] The general lesson repeats
[a documented surface is not a wired one](/findings/declared-but-unwired-engine-surfaces.md):
a recording that stands in for the slow part also stands in for its ordering.

# The fix and its shape

The engine already treats `closed` as terminal where it releases
dependencies,[^deps] so the operator's fourth source patch adds the same status
to the one check that lacks it, consulting `closed` only on the quiescent
branch. Admission refuses an engine without it, because the failure mode is a
silent hang rather than an error. Upstream enabler #8 in the operator plan
tracks the permanent fix.

[^close]: The store archives a verified, merged task to CLOSED
[^selfstop]: The self-stop's terminal check reads only done/failed
[^fetch]: fetch_all_tasks omits closed by default
[^deps]: Dependency release already counts closed as terminal
[^measured]: First real operator build, 2026-09-10

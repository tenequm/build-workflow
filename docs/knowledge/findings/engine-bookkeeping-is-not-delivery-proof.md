---
type: Finding
title: Native task bookkeeping contradicts its own delivered work, so only the driver's proofs can gate a phase
description: Across the first real operator builds the engine landed scored work while recording the attempt failed, refused a first attempt and delivered its retry, dropped owned_files from every retry, and left a superseded retry claimed at self-stop. Each looks like tampering to a driver that reads task status as truth; each is normal engine behavior around retries. The phase boundary must rest on scorer receipts, merge ancestry and journal events, with status used only where nothing else can answer.
tags: [bernstein, orchestration, retries, delivery, phase-boundary]
status: stable
stale_after: "2027-03-10T00:00:00Z"
generated: { by: claude-code/opus-5, at: "2026-09-10T18:20:00Z" }
sources:
  - id: builds
    resource: The first real operator builds (textkit.slugify fixture), 2026-09-10
    title: Seven runs with Claude Sonnet and Codex executors, agy and Claude ACP judges
  - id: reap
    resource: https://github.com/sipyourdrink-ltd/bernstein/blob/0a6bf9f2d/src/bernstein/core/agents/spawner_merge.py
    title: Dead-agent reaping merges an agent branch outside the live verification path
  - id: retry
    resource: https://github.com/sipyourdrink-ltd/bernstein/blob/0a6bf9f2d/src/bernstein/core/tasks/task_lifecycle.py
    title: retry_or_fail_task creates the retry; the new task carries no owned_files
  - id: janitor
    resource: https://github.com/sipyourdrink-ltd/bernstein/blob/0a6bf9f2d/src/bernstein/core/quality/janitor.py
    title: _check_file_contains verifies a completion signal, and an unmet one reopens the step
---

# Finding

Four distinct contradictions appeared in the first builds that ran real
executors, each of which the driver first read as an integrity failure and
parked on:[^builds]

1. **Landed work whose task says failed.** An attempt wrote the code, earned a
   scorer PASS, and merged; the engine then judged its session dead, marked
   that task `failed` and retried it. The retry found nothing left to do and
   completed. The content in the branch is fully proven; only the bookkeeping
   about the session says otherwise.[^reap]
2. **A refused attempt beside a delivered one.** A misdispatched first attempt
   had its branch refused by the gates and left a `refused_merges.jsonl` row.
   Its retry delivered. Reading any refusal in the run as unresolved evidence
   makes every first-attempt failure fatal, in a design that deliberately keeps
   native retries enabled.
3. **Retries drop the frozen scope.** A retry of a three-file step carried
   `owned_files: []`.[^retry] Ownership is enforced by the scorer from the
   frozen plan, not from the task record, so the emptied field changes nothing
   about what may be written - but an identity check comparing the retry to its
   admitted parent sees a scope change.
4. **A superseded retry left claimed at self-stop.** The janitor reopens a step
   whose completion signal is unmet (commonly: the executor never wrote its
   report),[^janitor] and a retry dispatched after the work already landed is
   refused by the scorer for having no content-bound PASS. The scheduler then
   self-stops with that retry still `claimed`.

# What the boundary may rest on

Scorer receipts (content-bound, archived per attempt), merge ancestry (the
second parent of an integration merge equals a scored head), the journal's
`run_completed`/`run_quiescence` pair, and the driver's own launch and POST
receipts. Those are the artifacts the driver produces or verifies itself.

Task status answers exactly one question it alone can answer - whether an
expected step ever reached a terminal state - and even there the honest
predicate is per logical step across its retry chain, not per task row. Every
tolerance added for the four cases above is bounded the same way: it accepts
the engine losing or contradicting its own record, and never accepts a step
that has no delivery proof, a merge with no scored parent, or a widened scope.

# A related engine side effect

On terminal failure the engine writes an incident case into
`src/bernstein/eval/cases/incidents/<id>.yaml` **relative to the workspace
root**, which lands as an untracked authored file in the user's repository and
parks the build's cleanliness check. It is engine output, not executor work.

[^builds]: The first real operator builds, 2026-09-10
[^reap]: Dead-agent reaping merges outside live verification
[^retry]: The retry path does not carry owned_files
[^janitor]: An unmet completion signal reopens the step

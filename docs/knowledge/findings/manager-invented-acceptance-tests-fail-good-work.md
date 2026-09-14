---
type: Finding
title: A manager-invented acceptance test can fail work that satisfied its task
description: Two historical /review-pr cases had managers tell lens workers to publish through one channel while testing an invented file path, so completed work failed and retried. The current manager prompt requires each completion signal to test the artifact named in that worker's task; the incident remains the reason that task/deliverable identity is explicit.
tags: [review-pr, bernstein, goal-text, orchestration]
status: stable
stale_after: "2027-03-12T00:00:00Z"
generated: { by: codex-cli/gpt-5, at: "2026-09-14T20:58:00Z" }
sources:
  - id: case01
    resource: "/tmp/review-eval-20260912T004119Z/floor/case-01/repo/.sdd/runtime/spawner.log - 8 lines of the form `FAIL: command='test -s /tmp/bernstein-review-fcab491854be/lens5.md' ...`, against 1 TRANSPORT FAILURE and 0 SUSPICIOUS clean exits; tasks.jsonl for the same run shows 25 task records covering 6 logical tasks, 14 of them failed"
    title: case-01, where retries were the dominant cost
  - id: case02
    resource: "/tmp/review-eval-20260912T004119Z/floor/case-02/repo/.sdd/runtime/spawner.log - the same failure with a different invented path, `test -s /tmp/bernstein-pr-review/findings/lens5-cleanliness-...`"
    title: case-02, a different invented path
  - id: manager
    resource: /skills/review-pr/templates/bernstein-templates/roles/manager/system_prompt.md
    title: the current and sole model-facing owner of the completion-signal rule
---

# Finding

The historical review goal handed the lead five lenses without fixing their handoff
contract. The lead did two things with that freedom: it wrote each worker a task whose
instructions end in `bernstein memory share lens-N-finding-1 ...`, and it attaches to the
same task an acceptance command that tests for a FILE - `test -s
/tmp/bernstein-review-<run-id>/lens5.md`.[^case01] The worker follows the instructions it
was given, shares its findings through the KB, and exits. The janitor then runs the
acceptance command, finds no such file, and fails the task.

The work was done. The evidence was published where the lead asked for it. The task fails
anyway, the lineage retries, and the retry spends a second full agent on a lens that was
already reviewed.

It is not a one-off wording accident: two cases in the same run produced two different
invented paths.[^case01][^case02] The lead is filling a gap the goal leaves open rather
than making a mistake, which is why it cannot be fixed by telling one model to be more
careful.

The cost is measured in wall time, and on a slow local lane that is the whole budget:
case-01's 25 task records cover 6 logical tasks, 14 of them failed, and the run was still
inside its merge step at the one-hour mark.[^case01] Eight of those failures are this
one cause.

The closure is the manager's task contract: every completion signal must test the
artifact requested from that worker.[^manager] The goal now contains only the five
lenses and no completion-signal protocol. This is orchestration, not advice about how
carefully a model should improvise.

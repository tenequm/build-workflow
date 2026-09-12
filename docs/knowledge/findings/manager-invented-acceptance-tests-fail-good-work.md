---
type: Finding
title: The lead invents a file-existence acceptance test the workers were never told to satisfy
description: In a /review-pr run the manager tells each lens worker to publish findings through the shared KB, then attaches an acceptance check like `test -s /tmp/bernstein-review-<id>/lens5.md` to the same task - so a lens that did its work and shared it correctly is failed on a file nobody asked for, retried, and charged a second full agent; observed on two cases with two different invented paths.
tags: [review-pr, bernstein, goal-text, orchestration]
status: stable
stale_after: "2027-03-12T00:00:00Z"
generated: { by: claude-code/opus-5, at: "2026-09-12T02:00:00Z" }
sources:
  - id: case01
    resource: "/tmp/review-eval-20260912T004119Z/floor/case-01/repo/.sdd/runtime/spawner.log - 8 lines of the form `FAIL: command='test -s /tmp/bernstein-review-fcab491854be/lens5.md' ...`, against 1 TRANSPORT FAILURE and 0 SUSPICIOUS clean exits; tasks.jsonl for the same run shows 25 task records covering 6 logical tasks, 14 of them failed"
    title: case-01, where retries were the dominant cost
  - id: case02
    resource: "/tmp/review-eval-20260912T004119Z/floor/case-02/repo/.sdd/runtime/spawner.log - the same failure with a different invented path, `test -s /tmp/bernstein-pr-review/findings/lens5-cleanliness-...`"
    title: case-02, a different invented path
  - id: goal
    resource: /skills/review-pr/templates/review-goal.md
    title: the goal text, which delegates the split and says nothing about acceptance checks
---

# Finding

The review goal hands the lead the five lenses and says how it splits them is its own
business. The lead does two things with that freedom: it writes each worker a task whose
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

The lever is the goal text, which is this skill's to change: it can state that a task's
acceptance check has to be the artifact the lead asked that worker to produce.[^goal] That
is a change to the doctrine file, so it is proven against the frozen corpus before it
ships, not argued.

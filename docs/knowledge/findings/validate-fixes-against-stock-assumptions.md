---
type: Finding
title: A fix proven in our environment is not proven for stock Bernstein
description: Pre-submission adversarial validation of three locally-proven engine fixes found one that would false-positive on every clean exit in stock target repos and disproved the premise of half of another - defects invisible in our environment because our repos share a gitignore assumption stock targets lack.
tags: [bernstein, upstream, validation, testing]
status: stable
generated: { by: claude-code/fable-5, at: "2026-09-07T15:02:00Z" }
sources:
  - id: issue5620
    resource: https://github.com/sipyourdrink-ltd/bernstein/issues/5620
    title: "salvage: git add -A stages the orchestrator's own .claude/settings.local.json into every [WIP] commit"
  - id: pr5619
    resource: https://github.com/sipyourdrink-ltd/bernstein/pull/5619
    title: The uncommitted-work fix as submitted, with the artefact filter the validation forced
  - id: pr5622
    resource: https://github.com/sipyourdrink-ltd/bernstein/pull/5622
    title: The retry-window fix as submitted, whose Verification section records the disproven earlier revision
---

# Finding

Three engine fixes had each run correctly through real builds in this
project's repositories, and on 2026-09-07 an adversarial validation pass -
one reviewer per fix, instructed to break the fix rather than confirm it -
was run before submitting them upstream. It found:

1. **A blocking false positive in a "proven" fix.** The uncommitted-work
   guard read `git status --porcelain` in the dead agent's worktree; but the
   engine's Claude adapter writes `.claude/settings.local.json` into every
   executor worktree before the agent starts, and no exclusion list covers
   that path. In any target repo that does not gitignore `.claude/`, every
   clean exit reads dirty and every Claude executor gets failed, retried to
   exhaustion, and dead-lettered. The defect was invisible in months of local
   use because Bernstein's own repository and ours all gitignore `.claude/` -
   while the engine's stated operating envelope is arbitrary target repos
   that do not.[^pr5619][^issue5620]
2. **A disproven premise in another.** Half of the retry-window fix rested on
   the claim that the orchestrator's stall backstop was permanently dead once
   any task had finished; driving the real tick loop showed the backstop's
   caller is gated so the claimed dead path cannot fire, the incident had
   ended through a different path, and the "fix" would have let the backstop
   kill runs that made progress seconds earlier. That half was dropped before
   submission.[^pr5622]

# The rule it supports

Local production use proves a fix against one environment's assumptions, not
against the target system's operating envelope. Before upstreaming a fix,
enumerate the assumptions the local environment shares that stock consumers
do not (here: a gitignore entry), and run an adversarial pass whose brief is
to break the fix - including driving the real code path the fix's premise
describes, not just the tests written for it. Both defects above were found
by exactly those two moves, and neither would have been caught by re-running
the fix's own green tests.

[^issue5620]: The salvage-side sibling of the same exclusion gap, filed upstream
[^pr5619]: The fix as submitted, carrying the artefact filter
[^pr5622]: The fix as submitted, whose Verification section records the dropped half

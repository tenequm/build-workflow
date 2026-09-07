---
type: Finding
title: Codex turns can be silently truncated by its content filter, presenting as clean completion
description: OpenAI's codex harness can kill a turn mid-task over benign vocabulary (race, sweep, exploit, attack) in filenames, comments, or prompts; the truncated turn ends looking like a normal completion, so a codex executor can exit 0 with its work incomplete.
tags: [codex, executors, reliability, briefs]
status: stable
stale_after: "2027-03-01T00:00:00Z"
generated: { by: claude-code/fable-5, at: "2026-09-07T15:17:00Z" }
sources:
  - id: observed
    resource: operator-driven codex sessions of 2026-09-07 preparing the upstream TUI fix (transcripts not in this repository)
    title: Two codex turns killed by the filter on a benign timing-validation script
  - id: pr5619
    resource: https://github.com/sipyourdrink-ltd/bernstein/pull/5619
    title: The engine guard that catches a clean exit with uncommitted work
  - id: pr5618
    resource: https://github.com/sipyourdrink-ltd/bernstein/pull/5618
    title: The engine guard that keeps exit-0 sessions off the log-pattern fast-fail path
---

# Finding

OpenAI's codex harness applies a server-side content filter that can end a
turn mid-task with a "flagged for possible cybersecurity risk" notice on
entirely benign work. Observed twice on 2026-09-07: a local TUI
timing-validation script was flagged, apparently on vocabulary alone -
words like "race", "sweep", "teardown" in the filename and comments -
and each time the turn stopped at that point while ending with a
normal-looking completion (an ordinary end-of-turn, exit 0).[^observed]

The deceptive completion is the dangerous half. This workflow dispatches
codex as its executor roles, and a filter-truncated executor produces
exactly the failure shape the engine finds hardest: a clean exit whose work
is partially done - written but uncommitted files, or a task abandoned
midway with no error signal.

# Consequences for this workflow

- **Brief vocabulary is an authorable risk surface.** Step titles, briefs,
  and file names are where a plan author controls the trigger words. Builds
  on security-adjacent code, or briefs that casually say "exploit the race"
  or "attack the problem", raise the odds of executors dying mid-task.
  Prefer neutral phrasing in briefs where it costs nothing.
- **The engine's clean-exit guards are the mitigation, not a nicety.** A
  truncated executor that exits 0 with uncommitted work is caught by the
  uncommitted-work veto and routed to a retry instead of being recorded as
  "no changes needed";[^pr5619] an exit-0 session is also kept off the
  log-pattern fast-fail path, which matters here because a filter notice in
  the transcript is precisely the kind of text a pattern scanner
  misreads.[^pr5618] The engine's ordinary retry is the recovery.

# Evidence limits

The observing transcripts are not in this repository, and the filter is
third-party behavior that can change without notice - hence the
`stale_after`. The finding's operational advice (neutral brief vocabulary,
rely on the clean-exit guards) is cheap even if the filter softens.

[^observed]: Two codex turns killed by the filter on a benign timing-validation script
[^pr5619]: The uncommitted-work veto submitted upstream
[^pr5618]: The exit-0 log-pattern guard submitted upstream

---
type: Decision
title: Every step's completion signal names the report the step must commit
description: A step whose signals name only its code can pass while its report is missing, because the report is what the scorer archives and the judge reads. The two builds that reached build_completed declared a file_contains signal on the report; the runs that parked did not, and a judge correctly raised the absent report as a defect its pinned fix scope could not repair.
tags: [plans, completion-signals, briefs, judging]
status: stable
generated: { by: claude-code/opus-5, at: "2026-09-10T20:12:00Z" }
sources:
  - id: parked
    resource: Operator build on the textkit.slugify fixture, 2026-09-10
    title: "Judge verdict: the implement step's report was never created in any commit reachable from TIP, out of scope for the regression fix"
  - id: completed
    resource: Two single-phase builds carried to build_completed, 2026-09-10
    title: Both declared file_contains on `reports/<step>.md :: Validation:` and delivered the report
  - id: template
    resource: /skills/build-plan/templates/brief.md
    title: The brief template's Report section, which now demands the literal the signal checks
---

# Decision

Every executor and fix step declares a `file_contains` completion signal naming
its own report path and a literal the report must contain. A step that changes
code declares both: the code witness and the report witness.

# Why

The report is not a courtesy. The scorer archives it per attempt and scores its
claims against the measured gate, and the blind judge reads it as the step's
account of what happened. A step whose signals name only its source file
therefore passes with its report missing, and the defect surfaces one phase
later in a judge verdict that the phase's pinned fix scope cannot repair - which
parks the build after the paid work is already done.[^parked] Both builds that
reached `build_completed` declared the report witness and produced it.[^completed]

The corollary the same evidence forced: the literal in the signal must be a
literal the brief actually asks for. The plan template checked for `Validation:`
while the brief asked for a `## Validation` section, so a correct executor
satisfied the brief and failed its own witness. The brief template now names the
exact literal.[^template]

# Cost of the rule

One line per step in the machine plan, and a step that genuinely writes no
report (none exist in the current templates) would need a different witness.
Against that: the failure it prevents costs a whole phase of executor and judge
spend, and surfaces as an out-of-scope finding rather than as a missing file.

[^parked]: The judge verdict naming the absent report
[^completed]: The two completed builds and their declared witnesses
[^template]: The brief template's Report section

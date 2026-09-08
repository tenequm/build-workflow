---
type: Finding
title: Plan-file completion signals are silently dropped at task POST
description: Bernstein's plan-post helper builds the POST body field by field and omits completion_signals, so witnesses declared in a plan YAML never reach the task server via `run --from-plan` - the janitor then verifies signal-less tasks by default heuristics, and the loss is invisible.
tags: [bernstein, witnesses, plan-loader, upstream-defect]
status: stable
stale_after: "2027-03-08T00:00:00Z"
generated: { by: codex/gpt-6, at: "2026-09-08T11:24:53Z" }
sources:
  - id: helper
    resource: https://github.com/sipyourdrink-ltd/bernstein/blob/0a6bf9f2d/src/bernstein/core/planning/planner.py
    title: _post_task_to_server builds the body field by field with no completion_signals key (~43-124)
  - id: schema
    resource: https://github.com/sipyourdrink-ltd/bernstein/blob/0a6bf9f2d/src/bernstein/core/server/server_models.py
    title: TaskCreate accepts completion_signals - the server can store them; only the helper drops them (~136-183)
  - id: default-verify
    resource: https://github.com/sipyourdrink-ltd/bernstein/blob/0a6bf9f2d/src/bernstein/core/tasks/task_lifecycle.py
    title: Signal-less coding tasks pass default verification (~4808-4821)
  - id: probe
    resource: operator's session scratch, adversarial gpt-6-astra review round 3 with an executed helper probe (not in this repository)
    title: Probe - input task carried one file_contains signal, the serialized POST carried none, 2026-09-08
  - id: plan
    resource: ../../plans/2609-08-bernstein-operator.md
    title: Readiness compares declared and loaded signals; the launch transaction verifies stored task payloads
---

# Finding

`_post_task_to_server` - the path every `bernstein run --from-plan`
invocation uses - constructs its POST body explicitly, forwarding title,
description, role, files, dependencies, model/effort/CLI, and
`context_files`, and **omitting `completion_signals` entirely**.[^helper]
An executed probe with a real `Task` carrying one `file_contains` signal
confirmed the serialized POST contained none.[^probe] The server schema
accepts the field, so a client that builds the full body itself is
unaffected - the drop is purely in the helper.[^schema]

The loss is invisible: a task with no declared signals falls through to
default verification for coding tasks, which passes on generic
heuristics.[^default-verify] Witnesses authored in plan YAML therefore
appear to work while never being checked.

# Consequence

Two separate hazards, one per audience:

- **This workflow**: build-run must POST tasks directly with the full
  payload (part of the launch transaction in
  [the phase-boundary decision](/decisions/phase-boundary-between-engine-runs.md));
  build-plan checks declared versus loaded signals at readiness, and
  build-run verifies the frozen payload against the *stored server task*
  after POST and before scheduler startup. These check different links
  in the chain; successful YAML loading cannot prove wire delivery.[^plan]
- **Any Bernstein user**: every plan-file witness is dead on arrival at
  this commit. Filed as an upstream enabler; `stale_after` marks when to
  re-check whether the fix landed.

Related shape trap in the same pipeline: the plan loader collapses
`{path, contains}` to the path alone while the janitor requires
`value: "path :: needle"` - so even after the POST is fixed, only the
`value` shape actually evaluates.

[^helper]: [_post_task_to_server builds the body field by field with no completion_signals key (~43-124)](https://github.com/sipyourdrink-ltd/bernstein/blob/0a6bf9f2d/src/bernstein/core/planning/planner.py)
[^schema]: [TaskCreate accepts completion_signals - the server can store them; only the helper drops them (~136-183)](https://github.com/sipyourdrink-ltd/bernstein/blob/0a6bf9f2d/src/bernstein/core/server/server_models.py)
[^default-verify]: [Signal-less coding tasks pass default verification (~4808-4821)](https://github.com/sipyourdrink-ltd/bernstein/blob/0a6bf9f2d/src/bernstein/core/tasks/task_lifecycle.py)
[^probe]: Probe - input task carried one file_contains signal, the serialized POST carried none, 2026-09-08. Source: operator's session scratch, adversarial gpt-6-astra review round 3 with an executed helper probe (not in this repository).
[^plan]: [Readiness compares declared and loaded signals; the launch transaction verifies stored task payloads](../../plans/2609-08-bernstein-operator.md)

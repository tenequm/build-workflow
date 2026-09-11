---
type: Finding
title: On a non-Claude ACP agent, acpx applies --model only if the agent advertises its models
description: acpx refuses a session with "Cannot apply --model" unless a non-Claude ACP agent advertises models in its session/new result; a configOptions entry for the same thing is not accepted by acpx 0.15.1, so any locally built ACP agent - a recording agent in a test, or a wrapper around a real server - must return the legacy models metadata or every acp-transport session dies before its first turn.
tags: [acpx, acp, review-pr, testing]
status: stable
stale_after: "2026-03-11T00:00:00Z"
generated: { by: claude-code/opus-5, at: "2026-09-11T03:40:00Z" }
sources:
  - id: measured
    resource: "Measured 2026-09-11 against acpx 0.15.1 on this workspace: three candidate advertisement shapes driven through a stub ACP agent"
    title: Direct experiment - configOptions refused, models accepted, both accepted
  - id: acpxdoc
    resource: "acpx --skill show acpx, Prompting flags and Model selection sections (acpx 0.15.1)"
    title: "--model <id>: non-Claude agents must advertise a model config option or legacy `models` metadata"
  - id: agent
    resource: ../../../fixtures/review-pr/recording_agent.py
    title: The recording agent that has to satisfy this, and the comment recording why
  - id: acp
    resource: ../../../skills/build-run/scripts/operator_driver/acp.py
    title: judge_argv - the acp transport passes --model to acpx rather than through the Claude bridge
---

# What happens

The `claude` transport binds its model through session metadata in the bridge, so it is
unaffected. The `acp` transport - every other family, including Codex and Antigravity -
passes `--model <id>` to `acpx` itself.[^acp] acpx then requires the agent to have
advertised that model, and an agent that has not fails the whole session after
`session/new` succeeds:

    error: Cannot apply --model "gpt-5.6-sol": the ACP agent did not advertise model
    support through a session config option or legacy models metadata, and the adapter
    does not support a startup model flag.

The session exits 1 having produced nothing. Under a workflow that enforces a
report-witness law this surfaces honestly - a missing report, retried once, then
recorded - but the failure text lives in the ACP transcript, not in the workflow's own
error, so the symptom presented is "this family never produces a report" for every
`acp`-transport lens at once.

# What acpx accepts

Measured directly against acpx 0.15.1 with a stub agent returning each shape in turn:[^measured]

| advertised in `session/new` result | acpx accepts `--model` |
|---|---|
| `configOptions: [{id: "model", type: "select", availableValues: [...]}]` | no |
| `models: {currentModelId, availableModels: [{modelId, name}]}` | yes |
| both | yes |

acpx's own reference says "a model config option or legacy `models` metadata",[^acpxdoc]
so the config-option path is presumably for a shape this stub did not guess; the legacy
`models` object is the one that demonstrably works, and it is one field.

# Who this bites

Not a real Codex or Antigravity server - both advertise. It bites anything locally
built that sits on the `acp` transport: a recording agent standing in for a provider in
a test, a wrapper script around a signed server, or a new family added to a stage
template. The fix is to return the `models` object from `session/new` and to answer
`session/set_model` and `session/set_config_option` with `{}`.[^agent]

Marked with a review date because it is a property of an external tool at a version: a
later acpx may accept the config-option shape, and the table above should be re-measured
rather than trusted after that.

---
type: Finding
title: A documented Bernstein surface is not a wired one - verify the production fire site
description: Six engine surfaces exist in source with docs, enums, routes, or CLI flags yet execute nowhere on the plan-run path; one conditional dispatcher assumed absent is wired and default-ON - so both absence and presence must be proven at the call site, never inferred from declarations.
tags: [bernstein, verification-discipline, engine-audit]
status: stable
stale_after: "2027-03-08T00:00:00Z"
generated: { by: codex/gpt-6, at: "2026-09-08T11:24:53Z" }
sources:
  - id: hooks
    resource: https://github.com/sipyourdrink-ltd/bernstein/blob/0a6bf9f2d/src/bernstein/core/lifecycle/hooks.py
    title: LifecycleEvent enum and script registry (POST_MERGE at line 84)
  - id: tracker
    resource: https://github.com/sipyourdrink-ltd/bernstein/blob/0a6bf9f2d/src/bernstein/core/orchestration/tracker_pipeline.py
    title: The tree's only lifecycle-hook fire site - POST_TASK from the external-tracker pipeline (~2276)
  - id: sse
    resource: https://github.com/sipyourdrink-ltd/bernstein/blob/0a6bf9f2d/src/bernstein/core/server/server_app.py
    title: The SSE bus publishes only task_update/agent_update strings (~1052)
  - id: parser
    resource: https://github.com/sipyourdrink-ltd/bernstein/blob/0a6bf9f2d/src/bernstein/core/config/seed_parser.py
    title: Pipeline step names outside VALID_GATE_NAMES raise SeedError (~1946); orchestration.test_followup defaults true (~1595)
  - id: followup
    resource: https://github.com/sipyourdrink-ltd/bernstein/blob/0a6bf9f2d/src/bernstein/core/orchestration/orchestrator.py
    title: Pre-stop test follow-up POSTs an unplanned qa task (~2578, ~2922)
  - id: followup-policy
    resource: https://github.com/sipyourdrink-ltd/bernstein/blob/0a6bf9f2d/src/bernstein/core/orchestration/test_followup.py
    title: Follow-up criterion, surviving-branch resolution, and environment-first enablement (~134-275)
  - id: reviews
    resource: operator's session scratch, adversarial gpt-6-astra review rounds 1-4 (not in this repository)
    title: Independent adversarial verification of the same inventory, 2026-09-08
---

# Finding

Audited at engine commit `0a6bf9f2d` (2026-09-08), each of these exists in
source - with documentation, an enum, a route, or CLI help text - and
executes nowhere on a plan run:

1. **Lifecycle hook bus**: `post_merge` and siblings are declared and
   subscribable, but no merge path dispatches any lifecycle event; the
   only fire site in the tree is `POST_TASK` from the external-tracker
   pipeline, and the orchestrator constructs no hook
   registry.[^hooks][^tracker]
2. **SSE event vocabulary**: the `run.completed`/`gate_result`/... event
   factories have no producer; the wire carries only `task_update` and
   `agent_update`.[^sse]
3. **Workflow DSL conditional edges**: no runtime caller; `workflow run`
   refuses DSL manifests outright.
4. **`ReviewGate`**: exported, zero consumers outside its own package.
5. **`--approval`/`--merge` CLI flags**: declared with help text, received
   into the run signature, forwarded nowhere; the yaml keys validate but
   never reach runtime config.
6. **yaml `pipeline:` with plugin gate names**: rejected at seed parse
   before plugin discovery, making entry-point gate plugins unreachable
   from `bernstein.yaml`.[^parser]

The rule cuts both ways: the pre-stop **test follow-up** - a conditional
task dispatcher everyone assumed the deterministic engine lacked - is
wired, default-ON, and POSTs an unplanned, signal-less `qa` task at the
quiescence check.[^followup][^parser] It requires a surviving completed-task
agent branch whose diff touches `src/` without `tests/`; normal cleanup can
remove the candidate, so not every source-only run triggers it. The task
has `metadata.origin: test_followup`, not retry lineage. Setting
`orchestration.test_followup: false` disables it only if an inherited
truthy `BERNSTEIN_TEST_FOLLOWUP` does not override the setting. A fixed-task
workflow therefore needs both configuration and launch-environment control,
not just the absence of importable backlog files.[^followup][^followup-policy]

# Rule

Before building on any engine surface, find its **production call site**
(not its definition, docs, or tests) and prove it fires on the path you
depend on; before assuming a behavior absent, check the config default in
the parser that actually reaches runtime. Four independent adversarial
review rounds converged on this inventory, and the first plan draft built
its central routing mechanism on item 1 before the rule was
applied.[^reviews]

[^hooks]: [LifecycleEvent enum and script registry (POST_MERGE at line 84)](https://github.com/sipyourdrink-ltd/bernstein/blob/0a6bf9f2d/src/bernstein/core/lifecycle/hooks.py)
[^tracker]: [The tree's only lifecycle-hook fire site - POST_TASK from the external-tracker pipeline (~2276)](https://github.com/sipyourdrink-ltd/bernstein/blob/0a6bf9f2d/src/bernstein/core/orchestration/tracker_pipeline.py)
[^sse]: [The SSE bus publishes only task_update/agent_update strings (~1052)](https://github.com/sipyourdrink-ltd/bernstein/blob/0a6bf9f2d/src/bernstein/core/server/server_app.py)
[^parser]: [Pipeline step names outside VALID_GATE_NAMES raise SeedError (~1946); orchestration.test_followup defaults true (~1595)](https://github.com/sipyourdrink-ltd/bernstein/blob/0a6bf9f2d/src/bernstein/core/config/seed_parser.py)
[^followup]: [Pre-stop test follow-up POSTs an unplanned qa task (~2578, ~2922)](https://github.com/sipyourdrink-ltd/bernstein/blob/0a6bf9f2d/src/bernstein/core/orchestration/orchestrator.py)
[^followup-policy]: [Follow-up criterion, surviving-branch resolution, and environment-first enablement (~134-275)](https://github.com/sipyourdrink-ltd/bernstein/blob/0a6bf9f2d/src/bernstein/core/orchestration/test_followup.py)
[^reviews]: Independent adversarial verification of the same inventory, 2026-09-08. Source: operator's session scratch, adversarial gpt-6-astra review rounds 1-4 (not in this repository).

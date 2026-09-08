---
type: Finding
title: Native merge evidence differs between live verification and dead-agent reaping
description: Dead-agent reaping can land work without a task_merged event, and merge gates receive a surrogate task ID; delivery requires a scored commit linked to an admitted attempt and exact Git ancestry.
tags: [bernstein, quality-gates, evidence, recovery]
status: stable
stale_after: "2026-10-08T00:00:00Z"
generated: { by: codex/gpt-6, at: "2026-09-08T13:40:15Z" }
sources:
  - id: merge
    resource: https://github.com/sipyourdrink-ltd/bernstein/blob/0a6bf9f2d/src/bernstein/core/agents/spawner_merge.py
    title: Merge gate constructs a surrogate Task from the session
  - id: lifecycle
    resource: https://github.com/sipyourdrink-ltd/bernstein/blob/0a6bf9f2d/src/bernstein/core/tasks/task_lifecycle.py
    title: record_task_merged belongs to the live verified-session path
  - id: tests
    resource: ../../../bernstein_operator/tests/test_native_phases.py
    title: Real native scheduler, server, gate, merge and closure with recording executors
  - id: proof
    resource: ../../../skills/build-run/scripts/operator_driver/reconcile.py
    title: Positive delivery proof and paired WAL closure
---

# Finding

The merge gate constructs a surrogate task whose title falls back to the
concrete task ID. A plugin cannot assume that the authored title available at
the earlier gate call site also arrives at merge time. The operator resolves
that ID through its frozen admission map and scope-preserving retry lineage;
unknown identities fail closed.[^merge][^tests]

Dead-agent reaping can land a branch before the later janitor sees a live
session. That path does not emit the `task_merged` event produced by the live
verified-session path. Requiring that event alone rejects delivered work;
accepting DONE alone accepts missing work.[^lifecycle][^tests]

When the event is absent, the operator requires a binary merge on the
integration branch's first-parent history whose second parent is exactly a
scorer-PASS head for one uniquely attributable `agent_spawned` attempt. It also
verifies terminal obligations, the receipt's tree and archived evidence, and
that every new commit is explained. Commit messages and similar trees do not
establish delivery.[^proof]

The lifecycle also leaves claim intents uncommitted in the WAL after writing a
committed `task_spawn_confirmed`. A fresh phase must not replay those intents
against its empty task store. After positive delivery and archival, the operator
seals only claim intents paired with a committed spawn, a journaled agent and
a terminal task; unknown or unpaired intents park.[^lifecycle][^proof][^tests]

[^merge]: [Native merge gate](https://github.com/sipyourdrink-ltd/bernstein/blob/0a6bf9f2d/src/bernstein/core/agents/spawner_merge.py).
[^lifecycle]: [Task lifecycle](https://github.com/sipyourdrink-ltd/bernstein/blob/0a6bf9f2d/src/bernstein/core/tasks/task_lifecycle.py).
[^tests]: [Native phase acceptance](../../../bernstein_operator/tests/test_native_phases.py).
[^proof]: [Delivery reconciliation](../../../skills/build-run/scripts/operator_driver/reconcile.py).

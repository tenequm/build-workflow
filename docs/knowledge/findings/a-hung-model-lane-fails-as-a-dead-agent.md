---
type: Finding
title: A spent or hung model lane surfaces as "agent died without output", not as an error
description: A CLI blocking on a refused quota produces a 0-token, 0-byte-log agent that bernstein reaps and its retrospective misattributes; the decisive diagnostic is a one-word one-shot probe of the lane, run before trusting any post-mortem.
tags: [bernstein, models, diagnosis]
status: stable
generated: { by: claude-code/opus-5, at: "2026-09-12T01:10:00Z" }
sources:
  - id: forensics
    resource: prove-run .sdd forensics on this host, 2026-09-11 19:25 UTC run - metrics showed 0 prompt/0 completion tokens across all calls, manager log 0 bytes, retrospective blamed the merge guard
    title: dead-agent forensics
  - id: probe
    resource: direct one-shot probes of the same model ids, same host, minutes later - "Rate limit exceeded" and "No payment method" surfaced immediately
    title: probe results
  - id: laundering
    resource: "/review-pr quality-lane cases 02 and 05, 2026-09-11 23:12Z and 23:38Z: every agent log under .sdd/runtime/agent_logs/*/ held exactly one line - `error: Individual quota reached. Please upgrade your subscription to increase your limits. Resets in 1h30m1s.` - while .sdd/runtime/dlq.jsonl recorded only `max_retries_exceeded` with `original_error` naming a dead agent and a failed janitor test, and no log in the run contained the string `quota`"
    title: the full laundering chain, measured on two cases
  - id: detector
    resource: /fixtures/review-pr-cases/harness.py
    title: lane_down(), the mechanical detector this finding produced
---

# Finding

When a provider refuses a request non-fatally (spent quota, missing billing),
some agent CLIs hang instead of exiting. Bernstein then observes only a
process that produced no output: it logs "agent died without output", meters
zero tokens, and its retrospective attributes the failed run to whatever else
it can see (in the observed case, the merge guard).[^forensics] Every layer
reports something true; none reports the cause.

The decisive, cheap diagnostic is to probe the lane directly with a one-word
one-shot prompt before believing any orchestrator post-mortem: the refusal
that the orchestration stack swallows surfaces immediately at the CLI.[^probe]
A lane probe belongs before any run whose failure would be expensive to
misread.

# What the refusal looks like by the time it reaches a scorer

Measured end to end on two review cases: each worker CLI wrote a single line -
`error: Individual quota reached ... Resets in 1h30m1s.` - and exited. Bernstein
has no classifier for that line, so the orchestrator recorded a dead agent, the
janitor test that reads the agent's shared memory failed as a consequence, the
task retried twice into the same wall, and the dead-letter queue finally recorded
`max_retries_exceeded` over a *janitor* failure. The word `quota` appears nowhere
in orchestrator.log, spawner.log, server.log or the debug log. Both cases ran a
full hour and billed nothing.[^laundering]

That matters to an eval harness specifically: a case whose lane was down produces
no report, and scoring it MISSED files a subscription outage as a model failure in
the regression ledger. The harness therefore reads the agent logs directly - if
every agent log in a run is a single `error:` line, the case is ERROR and carries
the refusal as its reason, and one agent with real output is enough to rule the
condition out. A refusal also cancels the cases that have not started, since the
next case would spend another full timeout discovering the same wall.[^detector]

[^forensics]: dead-agent forensics
[^probe]: probe results
[^laundering]: the full laundering chain, measured on two cases
[^detector]: lane_down(), the mechanical detector this finding produced

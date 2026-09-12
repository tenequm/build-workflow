---
type: Finding
title: A quiet pi turn under bernstein is killed at ~120s unless heartbeat floors are raised
description: pi writes zero bytes to a redirected stdout until the turn ends, and bernstein's worker heartbeat advances only when the agent log grows - untuned, SIGTERM lands at heartbeat_stale_s (120s) and SIGKILL 30s later, killing any long turn. The floors are a property of the seed, not of pi - a claude/agy quality seed shipped without the tuning block died the same way, on the same 90s liveness grace.
tags: [bernstein, pi, agy, claude, review-pr]
status: stable
stale_after: "2027-03-11T00:00:00Z"
generated: { by: claude-code/opus-5, at: "2026-09-11T22:35:00Z" }
sources:
  - id: worker
    resource: bernstein 3.19.1 core/orchestration/worker.py:280-314, core/defaults.py:201,215, core/agents/heartbeat.py:783-830
    title: log-growth heartbeat and escalation
  - id: measured
    resource: measured on this host with pi 0.85.1 - a 60s turn with two 25s bash calls wrote 0 bytes to a non-TTY stdout until completion; --mode json streamed 19KB by t=5s
    title: pi output behavior
  - id: seed
    resource: /skills/review-pr/templates/review-seed.yaml
    title: tuning floors in the review seed
  - id: quality
    resource: "preserved run at /tmp/review-eval-20260911T210735Z, quality seed (claude-sonnet-5 manager, agy gemini-3.7-flash-medium workers) carrying no tuning block, 2026-09-11 21:07-22:18Z"
    title: "liveness_judgment lines all read grace_s=90; SIGTERM at 120-131s of log silence; adapters.base Timeout after 900s on nine workers"
---

# Finding

Bernstein's worker heartbeat is log-growth-driven: the liveness stamp moves
only when new bytes arrive in the agent log.[^worker] pi in default text mode
writes nothing to a redirected stdout for the whole turn.[^measured] The
combination kills every quiet pi turn longer than the escalation window:
SIGTERM at heartbeat_stale_s (default 120s), SIGKILL 30s later. Short turns
pass, long turns die, and the deaths look like model failures.

Two mitigations, robust first: make pi's log grow (`--mode json` streams
continuously, but bernstein's pi adapter passes no flags, so it needs a PATH
shim), or raise the seed's tuning floors (max_agent_runtime_s,
heartbeat_stale_s, escalation_*, liveness_*) above the longest expected
turn - the review seed does the latter.[^seed]

# The floors belong to the seed, not to pi

The defaults are the engine's, so every lane inherits them and only the seed
overrides them. A quality seed written for the claude/agy lane and shipped
without a `tuning:` block reproduced this exactly: every `liveness_judgment`
line read `grace_s=90`, workers were SIGTERMed after 120-131s of log silence -
`heartbeat_age_s`, `log_age_s` and `git_age_s` all stale together, which is
what a model call in flight looks like - and nine more were killed by
`adapters.base` at the untuned 900s `max_agent_runtime_s`.[^quality] The deaths
then entered the retry machinery as agent failures and the run never
recovered.

The rule to carry: a seed without a `tuning:` block is a seed that has accepted
a 120s silence budget and a 900s turn budget for every role. Any new seed is
copied from one that has the floors, or it does not ship.

Related pi-adapter facts that ride the same seed: the adapter drops
`effort:` silently (thinking level must ride the model id's `:<level>`
suffix), and an unpinned `litellm/...` model id routes to the qwen adapter,
so `cli: pi` must be pinned.

[^worker]: log-growth heartbeat and escalation
[^measured]: pi output behavior
[^seed]: tuning floors in the review seed
[^quality]: the untuned quality seed died on the same 90s grace

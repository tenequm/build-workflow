---
type: Finding
title: On the pi lane the seed's effort key does nothing and the cli pin is load-bearing
description: bernstein's pi adapter builds `pi [--model <id>] <prompt>` and reads only the model from a role's config, so a seed's `effort:` is silently dropped - thinking level has to ride the model id suffix (`<id>:medium`) instead; and without an explicit `cli: pi` the adapter is chosen by model-name substring inference, which a litellm-prefixed local id does not resolve the way the seed intends.
tags: [bernstein, pi, review-pr, seed]
status: stable
stale_after: "2027-03-11T00:00:00Z"
generated: { by: claude-code/fable-5, at: "2026-09-11T22:20:00Z" }
sources:
  - id: adapter
    resource: bernstein 3.19.1 src/bernstein/adapters/pi.py - spawn() takes model_config (model plus effort) and builds cmd from model_config.model alone; its docstring documents mcp_config as Unused
    title: the pi adapter's argv
  - id: inference
    resource: bernstein 3.19.1 src/bernstein/core/agents/spawner_core.py:1665-1666 and _infer_adapter_name_for_provider (2890+) - "pin must never be overridden by model-name substring inference"
    title: adapter selection when nothing is pinned
  - id: session
    resource: "/review-pr path-A bring-up on this host, 2026-09-11: an unpinned litellm/ model id selected the wrong adapter until `cli: pi` was added to the seed and to every role in role_model_policy"
    title: observed during lane bring-up
  - id: seed
    resource: /skills/review-pr/templates/review-seed.yaml
    title: the review seed carrying both workarounds
---

# Finding

A role's `effort:` never reaches pi. The adapter receives the full model
config and constructs `pi [--model <id>] <prompt>` from the model field
only, so the key is accepted by the seed parser and silently discarded.[^adapter]
Thinking level has to travel inside the model id instead - `<id>:medium` -
which is pi's own suffix convention.

`cli: pi` is not decoration. When a role pins no CLI, bernstein picks the
adapter by substring inference over the model name; the pin exists
precisely to override that, as the spawner's own comment states.[^inference]
A `litellm/`-prefixed local gateway id is not a string that inference
resolves the way the seed intends, so the pin has to appear at the top
level and on every role in `role_model_policy`.[^session][^seed]

Both facts are invisible at run time: a dropped `effort:` and a
mis-inferred adapter produce a run that starts normally and only reads
wrong in the agent logs.

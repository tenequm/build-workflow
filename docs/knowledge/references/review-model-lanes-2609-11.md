---
type: Reference
title: The 2609-11 model-lane survey for /review-pr
description: A dated survey of the local pi, subscription, opencode Zen and metered Gemini routes considered for /review-pr on 2026-09-11, not the authority for current routing. The seed owns production routing; alternative-model comparisons are out-of-band Pond experiments and never roles, prompts or report inputs in the production review.
tags: [review-pr, models, providers, cost]
status: stable
stale_after: "2026-12-11T00:00:00Z"
generated: { by: codex-cli/gpt-5, at: "2026-09-14T20:45:00Z" }
sources:
  - id: survey
    resource: "Session research sweep of 2026-09-11: provider docs, Artificial Analysis index, Terminal-Bench listings, provider ToS pages, and the Meta muse-spark announcement"
    title: The model-options survey
  - id: gateway
    resource: "Operator measurement, 2026-09-11: the local LiteLLM gateway declared in ~/.pi/agent/models.json, serving qwen3.8-flash-next, qwen3.8-27b-nvfp4 and qwen3.6-35b-a3b-nvfp4 at 209, 78 and 54 tok/s"
    title: The local gateway and its throughput
  - id: lane
    resource: ../../../skills/review-pr/templates/review-seed.yaml
    title: The review seed, the sole authority for current production routing
  - id: fence
    resource: ../../../skills/review-pr/SKILL.md
    title: The fence every lane runs under
  - id: pidig
    resource: "Empirical pi redirect-and-sync runs of 2026-09-11 (pi 0.85.1, pond 0.17.2, pi-acp over acpx), plus a source read of the bernstein pi adapter at v3.19.2"
    title: The pi scoping dig
  - id: boundary
    resource: "Git commits c5a0ae1 and 711f340: shadow roles, model routes, role prompts and report handling were removed from /review-pr, then all four corpus cases recovered with a seven-task graph containing only manager, five production lenses and report writer"
    title: The out-of-band model-comparison boundary and proof
  - id: zenprobe
    resource: "Keyless probe runs of 2026-09-11 against the opencode Zen free catalogue over the real acpx transport, including a pond sync into a fresh per-run store"
    title: The opencode Zen probe (history)
  - id: zenprice
    resource: "The models.dev catalogue as opencode 1.18.30 cached it (~/.cache/opencode/models.json), read 2026-09-11"
    title: The Zen rate card (history)
---

# Authority and measurement boundary

This reference is a dated survey, not live routing state. The current
`review-seed.yaml` is the sole authority for which model serves each production
role.[^lane] A model comparison is run separately against the same lens text and
captured in Pond; it never adds a role, route, prompt, findings file, dependency or
report input to `/review-pr`. The shadow-free graph was checked in every case of the
four-case corpus proof.[^boundary]

# The two lanes surveyed on 2026-09-11

| lane | roles | models | cost | limits |
|---|---|---|---|---|
| local-first | all | `litellm/qwen3.8-flash-next`, `litellm/qwen3.8-27b-nvfp4`, `litellm/qwen3.6-35b-a3b-nvfp4` via the `pi` CLI | none | none - local hardware is the only ceiling |
| subscription quality | manager | `claude-sonnet-5` via the `claude` CLI | subscription quota | account limits |
| subscription quality | reviewer, security, qa | `gemini-3.7-flash-medium` via `agy` | subscription quota | account limits |

Both candidates were evaluated under the same fence: public repositories and this
repository's eval corpus only, with no GitHub token handed to a model session.[^fence]

# The local-first lane

`pi` (earendil-works, 0.85.1) pointed at a local LiteLLM gateway declared in
`~/.pi/agent/models.json`, whose ids are written `litellm/<id>` in a seed. Measured
throughput: `qwen3.8-flash-next` 209 tok/s, `qwen3.8-27b-nvfp4` 78 tok/s,
`qwen3.6-35b-a3b-nvfp4` 54 tok/s.[^gateway] The properties that matter for a review
loop are not the benchmark numbers: the lane costs nothing per run, has no rate limit
to storm against, and the prompts (diff, changed files, whatever context a lens opens)
never leave the machine, which is what removes the data-export question that fenced
the free hosted routes. Iteration speed on goal text and seed is therefore bounded by
tokens per second, not by quota or spend.

# The surveyed subscription quality lane

A `claude-sonnet-5` manager over `agy gemini-3.7-flash-medium` workers. The manager
decomposes the goal and drives the task server over curl, which punishes loose tool
discipline; the three lens roles are rubric-driven bulk reading, which is what flash
is for. Both halves are subscription-backed, so a run spends quota, never dollars.
Gemini flash's constraint is a 5-hour burst limiter, not quota exhaustion - that is
what caused the 429 storm which shaped the old runner's provider-failure detection,
so concurrency is a dial to ramp, never a place to start high.[^survey]

# Where the pi isolation findings live

The 2026-09-11 scoping dig established that session capture can be redirected without
moving the operator's own sessions, while config redirects do not isolate user-level
skills, extensions or MCP servers.[^pidig] The durable, current conclusions are kept
in the focused findings rather than duplicated here:

- [A reviewed tree can reconfigure its own reviewer](../findings/a-reviewed-tree-can-reconfigure-its-reviewer.md).
- [Unwrapped Bernstein agents boot the user's global MCP servers](../findings/spawned-agents-inherit-user-global-mcp-servers.md).
- [The pi lane's configuration rides the model ID](../findings/pi-lane-config-rides-the-model-id.md).

# History: the opencode Zen experiments, retired 2026-09-11

Everything in this section is the record of a lane that left the stack the same day
it was adopted; nothing here describes current routing. opencode was wired as the
multi-provider vehicle (ACP mode `opencode acp`, adapter argv
`[npx, --yes, opencode-ai@1.18.30, acp, --pure]`), its Zen free catalogue was probed
keylessly, and `review-seed.yaml` briefly routed manager, reviewer, security and qa
to `opencode/muse-spark-1.3-contributor-free` at `effort: high` - proven end to end
on 2026-09-11 (`floor/case-01` RECOVERED in 95.5s, no provider spend).[^zenprobe]
What was learned and is worth keeping:

- All seven Zen free models train on or retain prompts, which is why those routes
  were fenced to public repositories; the local lane removes the question rather
  than answering it.[^survey]
- Zen charged twice Google list for Gemini flash - $1.50/M in, $7.50/M out against
  Google's $0.75/$3.75; `glm-5.3-flash` at $0.15/$0.50 with a 1M context was the
  untested next cost lever if a hosted lane ever returns.[^zenprice]
- `pondcost` prices claude-code, codex-cli and agy sessions only, so an opencode
  session reported no dollars at all. Cost is observability, and a missing model
  prices to null by design.
- Rejected in the same sweep: `nemotron-3-ultra` (Terminal-Bench 1%, ~6 tok/s, terms
  that train on prompts and bar production use) and OpenRouter `:free` tiers, whose
  rate limits make them unusable as review lanes.[^survey]
- The opencode redirects did not clean the reviewer's context either: `--pure` plus
  both XDG redirects still loaded the operator's user-level skills, because those
  hang off `HOME`.[^zenprobe] The same class of leak is recorded above for pi.

# History: the metered gemini fallback lane

Also not current - the metered `GEMINI_API_KEY` was revoked on 2026-09-11. For the
day it comes back: the agy ACP server honours `GEMINI_HOME`, so a second tree whose
`antigravity-acp/settings.json` declares `gemini-api-key` auth is a fully isolated
lane - the subscription lane's oauth config is never touched, and unsetting two
environment variables restores it exactly. Both names sat on the session env
allowlist with an exposure-parity note: a session that can be talked into printing
its environment can equally read the subscription token file under `HOME`, so the
lane added no new leak class. Its binding limit was tokens per minute, not per
window: the API tier rejected a 7-cases-concurrent corpus run outright (429 on every
session) yet recovered a case cleanly run sequentially.[^survey]

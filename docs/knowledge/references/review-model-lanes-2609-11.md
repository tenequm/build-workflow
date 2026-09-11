---
type: Reference
title: Model lanes for /review-pr - the 2609-11 survey
description: The measured model-routing landscape for review lanes - opencode is the multi-provider vehicle (Zen free catalogue now, an OpenRouter key later), muse-spark-1.3-contributor-free is the adopted free trial pick, nemotron-3-ultra and OpenRouter :free tiers are rejected with reasons, pi is a proven-scopable fallback, and gemini flash economics anchor the paid fast loop.
tags: [review-pr, models, providers, cost]
status: stable
stale_after: "2026-12-11T00:00:00Z"
generated: { by: claude-code/fable-5, at: "2026-09-11T13:50:00Z" }
sources:
  - id: survey
    resource: "Session research sweep of 2026-09-11: provider docs, Artificial Analysis index, Terminal-Bench listings, provider ToS pages, and the Meta muse-spark announcement"
    title: The model-options survey
  - id: zenprobe
    resource: "Keyless probe runs of 2026-09-11 against the opencode Zen free catalogue over the real acpx transport, including a pond sync into a fresh per-run store"
    title: The opencode Zen probe
  - id: pidig
    resource: "Empirical pi redirect-and-sync runs of 2026-09-11 (pi 0.85.1, pond 0.17.2, pi-acp over acpx), plus a source read of the bernstein pi adapter at v3.19.2"
    title: The pi scoping dig
  - id: lane
    resource: ../../../skills/review-pr/templates/stages-opencode.yaml
    title: The committed opencode trial lane
  - id: policy
    resource: ../decisions/free-tier-models-are-open-source-only-lanes.md
    title: The open-source-only fence for free routes
---

# The vehicle

opencode is the one adapter worth wiring for multi-provider routing: its ACP
mode is first-party (`opencode acp`, adapter argv
`[npx, --yes, opencode-ai@1.18.30, acp, --pure]`), its Zen free catalogue
needs no credential at all, and the same lane takes an OpenRouter key later
without structural change.[^zenprobe] The lane is committed and
verified end to end, keylessly, including pond capture scoped by a
per-session `XDG_DATA_HOME` overlay with the model id and effort variant
preserved in the stored row.[^lane]

Mechanics that cost time to learn: the effort option id is `effort` (not
`reasoning_effort`; the wrong name is a -32602) and defaults to `minimal`;
and the XDG redirects do NOT clean the reviewer's context - `--pure` plus
both redirects still loads the operator's user-level skills, because those
hang off `HOME`.[^zenprobe]

# Verdicts

- **muse-spark-1.3-contributor-free: adopt as trial.** Artificial Analysis
  index 48 against Opus 5's 51, free on Zen, and the model behind the
  committed trial lane. All seven Zen free models train on or retain
  prompts, so every free route is fenced to open-source repositories.[^policy]
- **nemotron-3-ultra: skip.** Terminal-Bench 1%, ~6 tok/s, and terms that
  both train on prompts and bar production use.[^survey]
- **OpenRouter `:free` tiers: dead.** Rate limits make them unusable as
  review lanes; OpenRouter matters only as a paid key later, through the
  opencode lane.[^survey]
- **glm-5.3-flash: candidate, untested.** Noted for a later paid trial.[^survey]
- **gemini-3.7-flash-medium: the paid fast-loop anchor.** List price
  $0.75/M in, $3.75/M out; a lens session runs ~$0.12 and a 14-case corpus
  pass ~$5-8 at list, absorbed by the Antigravity subscription. Its 5-hour
  burst limiter, not quota exhaustion, caused the 429 storm that shaped the
  runner's provider-failure detection.[^survey]

# pi, the fallback - scopable after all

An earlier session-note claimed pond could not scope pi sessions per run.
Refuted empirically: pi (earendil-works, 0.85.1) has three documented
session-dir redirects with precedence (`--session-dir` flag >
`PI_CODING_AGENT_SESSION_DIR` > `sessionDir` setting), and pond's
`pi-coding-agent` adapter synced exactly one redirected session into a
fresh store while the host's existing sessions stayed untouched - both
directly and over the real acpx transport via the third-party `pi-acp`
adapter.[^pidig] Wiring it as a review family needs roughly six lines plus
a family block; config isolation additionally needs `PI_CODING_AGENT_DIR`,
because a pi session otherwise loads the operator's skills and extensions.

bernstein itself ships a `pi` adapter, but a shallow, dated one: it targets
the npm-deprecated pre-rename package and builds an interactive (not
headless) invocation, with an all-defaults strategy.[^pidig]

---
type: Reference
title: Model lanes for /review-pr - the 2609-11 survey
description: The measured model-routing landscape for review lanes - opencode Zen is the whole vehicle now (free catalogue for the fast loop, paid ids for production), muse-spark-1.3-contributor-free is the adopted free pick, Zen prices Gemini flash at twice Google list, nemotron-3-ultra and OpenRouter :free tiers are rejected with reasons, and pi is a scopable fallback that still leaks HOME.
tags: [review-pr, models, providers, cost]
status: stable
stale_after: "2026-12-11T00:00:00Z"
generated: { by: claude-code/opus-5, at: "2026-09-11T16:45:00Z" }
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
    resource: ../../../skills/review-pr/templates/stages-fast.yaml
    title: The fast loop, which is now the opencode Zen free lane
  - id: zenprice
    resource: "The models.dev catalogue as opencode 1.18.30 caches it (~/.cache/opencode/models.json), read 2026-09-11"
    title: The Zen rate card
  - id: pilane
    resource: ../../../skills/review-pr/templates/stages-pi.yaml
    title: The committed pi trial lane
  - id: policy
    resource: ../decisions/free-tier-models-are-open-source-only-lanes.md
    title: The open-source-only fence for free routes
---

# The vehicle

opencode is the one adapter worth wiring for multi-provider routing: its ACP
mode is first-party (`opencode acp`, adapter argv
`[npx, --yes, opencode-ai@1.18.30, acp, --pure]`), its Zen free catalogue was
probed keylessly, and the same lane takes an OpenRouter key later without
structural change.[^zenprobe] Whether a `-contributor-free` id still serves
without the account was not retested: the fast loop exports
`OPENCODE_API_KEY`, so it has not had to answer that question. The lane is committed and
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
- **glm-5.3-flash: candidate, untested - and the next cost lever.** $0.15/M
  in, $0.50/M out on Zen with a 1M context, which is a tenth of what Zen
  charges for Gemini flash. Measure it on the fast loop before it goes
  anywhere near production's third lane.[^zenprice]
- **gemini-3.7-flash-medium: no longer the fast-loop anchor.** Google list
  price $0.75/M in, $3.75/M out; a lens session runs ~$0.12 and a 14-case
  corpus pass ~$5-8 at list, absorbed by the Antigravity subscription while
  one existed. Its 5-hour burst limiter, not quota exhaustion, caused the 429
  storm that shaped the runner's provider-failure detection.[^survey]

# Where the lanes stand after 2026-09-11

The operator revoked the metered `GEMINI_API_KEY` and no template declares the
agy transport any more, so the section below is history for the day the key
comes back, not current routing. What runs now:

- **The fast loop IS the Zen free lane.** `stages-fast.yaml` runs every lens
  and the claims role on `opencode/muse-spark-1.3-contributor-free` at
  `effort: high`, with codex verifying (cross-family verification is refused
  same-family, and the OpenAI content filter on gating vocabulary parks loudly
  rather than passing silently). The earlier `stages-opencode.yaml` was folded
  into it: after the switch the two files differed in nothing but their
  bounds.[^lane] Proven end to end the same day - `floor/case-01` RECOVERED in
  95.5s, no provider spend.
- **Production's third lane is Zen-served Gemini.** `stages.yaml` keeps the
  family named `gemini`, because a family names the model family and not the
  transport, and points its adapter at `opencode acp --pure` with
  `opencode/gemini-3.8-flash` and `opencode/gemini-3.7-flash`. It is load
  bearing rather than latent: the gating lens forbids codex, so with only two
  other families it would lose its dual-family second opinion entirely.
- **Zen charges twice Google list for Gemini flash**: $1.50/M in, $7.50/M out
  against Google's $0.75/$3.75.[^zenprice] The swap bought one key, no local
  ACP wrapper and no metered Google account; it did not buy a lower rate. That
  is what makes glm-5.3-flash the next thing to measure.
- **The credential reaches a Zen session only as `OPENCODE_API_KEY`.**
  `opencode auth login` writes it under `XDG_DATA_HOME`, and every opencode
  family redirects that root per session to scope capture, so the env name (on
  the session allowlist, exposure parity as below) is the whole path.
- **A Zen lane's cost figure is null, not a floor.** `pondcost` prices
  claude-code, codex-cli and agy sessions only; there is no opencode branch, so
  an opencode session reports no dollars at all. Cost is observability and a
  missing model prices to null by design, but the production Gemini lane lost a
  figure it used to have.

# The metered gemini fallback lane

When the subscription window exhausts, the same agy ACP server runs on a plain
Gemini API key with no key rotation in the code: the server honours `GEMINI_HOME`,
so a second tree whose `antigravity-acp/settings.json` declares `gemini-api-key`
auth is a fully isolated lane - the subscription lane's oauth config is never
touched, and unsetting two environment variables restores it exactly. The two names
(`GEMINI_API_KEY`, `GEMINI_HOME`) are on the session env allowlist with an
exposure-parity note: a session that can be talked into printing its environment
can equally read the subscription token file under `HOME`, so the lane adds no new
leak class.[^survey]

The lane's constraint is per-minute, not per-window: the API tier rejected a
7-cases-concurrent corpus run outright (429 "exceeded your current quota" on every
session) yet recovered a case cleanly run sequentially - with ~120k-token briefs,
tokens per minute is the binding limit, so concurrency is a dial to ramp, never a
place to start high.[^survey]

# pi, the fallback - scopable after all

An earlier session-note claimed pond could not scope pi sessions per run.
Refuted empirically: pi (earendil-works, 0.85.1) has three documented
session-dir redirects with precedence (`--session-dir` flag >
`PI_CODING_AGENT_SESSION_DIR` > `sessionDir` setting), and pond's
`pi-coding-agent` adapter synced exactly one redirected session into a
fresh store while the host's existing sessions stayed untouched - both
directly and over the real acpx transport via the third-party `pi-acp`
adapter.[^pidig] It is now wired as a family: both roots are redirected per session
(`PI_CODING_AGENT_DIR` too, so the session opens on none of the operator's
providers and no saved project trust), capture points pond's
`pi-coding-agent` adapter straight at the redirected session root, and `.pi`
plus project `.agents/skills` are stripped from the reviewed tree.[^pilane]
The effort knob is pi-acp's `thought_level` - Codex's `reasoning_effort` is a
-32602 - and pi-acp rejects pi's own `max` level, accepting only off through
xhigh.

The config redirect is narrower than the earlier note claimed, and the gap is
larger than opencode's. Probed over the real acpx transport on 2026-09-11 with
both variables pointed at fresh directories: the session still loaded every
skill under `~/.agents/skills/` and still executed the operator's
`~/.pi/agent/extensions/*.ts`, from the very root `PI_CODING_AGENT_DIR` had
been pointed away from. Skills are text; an extension is TypeScript running in
the reviewer's process. pi has `--no-skills` and `--no-extensions`, but pi-acp
spawns a fixed `pi --mode rpc --no-themes` and forwards neither, so no family
block can close it - only a different adapter, or a session HOME of its
own, would.[^pidig]

bernstein itself ships a `pi` adapter, but a shallow, dated one: it targets
the npm-deprecated pre-rename package and builds an interactive (not
headless) invocation, with an all-defaults strategy.[^pidig]

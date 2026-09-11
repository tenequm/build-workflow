---
type: Reference
title: The 2609-02 research corpus - evals, lab guidance, literature, orchestrator survey
description: Where the project's evidence base lives - docs/research/2609-02-research-overview.md holds the measured executor evals, the Anthropic/OpenAI/Google lab guidance, the best-of-N/N-version/judge/speculation literature with links, the orchestrator survey that selected Bernstein, and the AVO invariants; plan citations resolve there.
tags: [research, evals, literature, provenance]
status: stable
generated: { by: claude-code/fable-5, at: "2026-09-11T00:00:00Z" }
sources:
  - id: overview
    resource: "docs/research/2609-02-research-overview.md"
    title: Research overview, 2026-09-02 (repo path)
---

# What it is

The dated snapshot that grounds this project's design choices: measured
executor eval rounds (Codex, Opus, Flash via agy), process findings that
generalise, lab-reported guidance from Anthropic, OpenAI and Google, the
paper literature on best-of-N, verifier ceilings, N-version independence,
LLM-as-judge biases and speculation, the orchestrator survey that selected
Bernstein, and the AVO/avo-lite invariants.[^overview]

# How to use it

Plans cite these results by claim ("per-bug rubric kappa 0.75",
"cross-family 43-44%"); the full links and numbers resolve in the
overview, not in the plans. It is a snapshot: stars, versions and model
names are as of 2026-09-02, and its own section 12 lists what was not
verified. Raw eval records live outside this repo, in the `personal`
repo under `docs/codex-subagents-herd-eval/`.

[^overview]: Research overview, 2026-09-02

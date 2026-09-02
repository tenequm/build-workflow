---
name: build-design
description: "Stage 1 of the build workflow: turn an idea into docs/spec.md. Interviews the user grill-me style, fans out section drafts to Opus subagents, runs one fresh critic over the spec for contradictions, converges when a critic round warrants no edits. Use when starting a big build from an idea, or when the spec must change. Triggers: /build-design, design the spec, start a build from an idea."
---

# build-design

Output: `docs/spec.md` (tracked; section numbers frozen once a plan cites them) and `.agents/build/runs/<run>/ledger.md` opened with the spec sha256.

1. Orient: read the repo's AGENTS.md/CLAUDE.md, the existing `docs/spec.md` if any, and the last run's `handoff.md`.
2. Interview: the questions that change the design, three to five, grill-me style. Decisions are recorded with the rejected alternative.
3. Draft: fan out section drafts to parallel Opus subagents (`model: opus`), each given the decisions and the sections it owns. The driver decides; subagents write.
4. Critic: one fresh Opus subagent, read-only, reads the whole spec and lists contradictions, undefined terms, invariants without a check. Blocking findings are edits; rerun until clean.
5. Close: commit `docs/spec.md`, write the run dir and ledger, offer `/build-plan <run dir>`.

Rules: ASCII only; the spec changes only through this skill; never mid-plan.

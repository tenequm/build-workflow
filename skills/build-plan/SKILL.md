---
name: build-plan
description: "Stage 2 of the build workflow: cut docs/spec.md into a Bernstein plan and per-step briefs. Writes .agents/build/plans/<slug>.yaml with stages, steps, owners, cli and model per step, and briefs plus interface contracts for parallel splits in the run dir. Use after /build-design or when a spec exists and a plan does not. Triggers: /build-plan, cut the plan, write briefs."
---

# build-plan

Input: a run dir with the spec sha256 in `ledger.md`. Output: `.agents/build/plans/<slug>.yaml`, `<run>/briefs/<step>.md`, `<run>/contracts/<seam>.md`.

1. Decompose by dependency graph, not by file list: independent subtasks run in parallel stages; a seam split gets a driver-written interface contract first. Phase length target 15-30 min of executor wall; split longer ones.
2. Assign executors by shape: seam and investigation steps -> herdr-claude / claude-opus-5; transfer, exact-line and fix steps -> herdr-codex; Flash only as the shadow lane (adapter flag).
3. Judge nodes: `judge-N` depends on `phase-N`; `fix-N` depends on `judge-N` with condition failed, retry 2; dependents depend on `phase-N` only. `polish-N` optional, non-blocking, files restricted to phase-N's.
4. Briefs from `templates/brief.md`: allowlist, items with done-criteria, exact validation commands, report format. Length cap; headers.
5. Write plan and briefs, record hashes in `ledger.md`, offer `/build-ready <run dir>`.

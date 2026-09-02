---
name: build-plan
description: "Stage 2 of the build workflow: cut docs/spec.md into a Bernstein plan and per-step briefs. Writes .agents/build/plans/<slug>.yaml with stages, steps, owners, cli and model per step, and briefs plus interface contracts for parallel splits in the run dir. Use after /build-design or when a spec exists and a plan does not. Triggers: /build-plan, cut the plan, write briefs."
---

# build-plan

Input: a run dir with the spec sha256 in `ledger.md`. Output: `.agents/build/plans/<slug>.yaml`, `<run>/briefs/<step>.md`, `<run>/contracts/<seam>.md`.

1. Decompose by dependency graph, not by file list: independent subtasks run in parallel stages; a seam split gets a driver-written interface contract first. Phase length target 15-30 min of executor wall; split longer ones.
2. One step per stage, stage name = step name, `depends_on` carries the DAG. Bernstein batches concurrently-open same-role tasks into ONE session (`max_tasks_per_agent` defaults to 2 and no seed key, `tuning:` section or run flag changes it), and a batched session spawns once, so only the first step's sidecar `cli` is ever read. What keeps two open siblings apart is a differing `cli:` or `model:` **in the plan** (`_groups_can_merge`, tick_pipeline.py:113-127); the sidecar `cli` is invisible to Bernstein. So declare `cli:` on every step in the plan too, and give two parallel siblings different roles if they would otherwise share role, cli and model.
3. Split a phase into parallel sibling steps by disjoint file ownership: whenever one step would own more than about 8 files, or two independent packages, cut it into `phase-Na`, `phase-Nb`, ... in stages of their own with no dependency between them. Siblings must not share a file -- readiness fails a plan where two steps own the same path or overlapping globs -- so a file both would touch (`go.mod`, a registry, a shared type) belongs to exactly one sibling or to a small preceding step that lands it first. `judge-N` depends on every sibling stage, so it reviews the whole phase.
4. Assign executors by shape: seam and investigation steps -> herdr-claude / claude-opus-5; transfer, exact-line and fix steps -> herdr-codex; Flash only as the shadow lane (adapter flag).
5. Judge nodes: `judge-N` depends on every `phase-N` sibling stage; `fix-N` depends on `judge-N` with condition failed, retry 2; dependents depend on `phase-N` only. `polish-N` optional, non-blocking, files restricted to phase-N's.
6. Briefs from `templates/brief.md` into `<run>/briefs/<step>.md`: allowlist, items with done-criteria, exact validation commands, report format. Judge steps use `templates/judge-brief.md`, fix steps `templates/fix-brief.md`. Length cap 16k; headers. The sidecar `<slug>.steps.yaml` (from `templates/build.steps.yaml`) maps each step title to its brief, report path, base, shadow lane and judge mode.
7. Write plan and briefs, record hashes in `ledger.md`, offer `/build-ready <run dir>`.

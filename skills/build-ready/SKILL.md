---
name: build-ready
description: "Stage 3 of the build workflow: the readiness gate. Runs the mechanical checklist (plan validate, allowlists exist, disjoint ownership, validation commands green on the base, spec citations resolve, done-criteria present) and one fresh Opus critic per brief; edits briefs; converges when a critic round warrants no edits. Use on any plan before /build-run, including plans written by hand. Triggers: /build-ready, is the plan ready, check the briefs."
---

# build-ready

Input: run dir. Output: `<run>/readiness/ledger.md` and `<run>/readiness/critic-<step>.md`, briefs edited in place, hashes updated in `ledger.md`.

1. Mechanical pass: `bernstein-herdr ready --plan .agents/build/plans/<slug>.yaml` runs `templates/readiness.md` as commands (plan validate, briefs present, disjoint ownership across siblings, spec citations resolve, Items/Report/Deviations sections, length cap, every Validation command executed on the base in a temporary worktree) and writes `<run>/readiness/ledger.md` plus `pins.json` (spec, plan, brief hashes). The adapter refuses to start any step whose pins changed. A RED validation command on the base is a brief error unless the brief names that red window.
2. Critic per brief: fresh Opus subagent, read-only, tries the first item in its head, reports underspecified points, spec contradictions, unvalidatable items, overlaps between briefs.
3. Edit briefs for blocking findings; rerun the critic; stop when a round warrants no edits. Two rounds is normal.
4. Record the spec sha256, plan hash and brief hashes; offer `/build-run <run dir>`.

Never start executors from this skill.

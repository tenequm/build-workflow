---
name: build-ready
description: "Stage 3 of the build workflow: the readiness gate. Runs the mechanical checklist (plan validate, allowlists exist, disjoint ownership, validation commands green on the base, spec citations resolve, done-criteria present) and one fresh Opus critic per brief; edits briefs; converges when a critic round warrants no edits. Use on any plan before /build-run, including plans written by hand. Triggers: /build-ready, is the plan ready, check the briefs."
---

# build-ready

Input: `<run>` = `.agents/build/runs/<slug>`. Output: `<run>/readiness/ledger.md`,
`<run>/readiness/pins.json`, `<run>/readiness/critic-<T>.md`, briefs edited in
place, a line in `<run>/ledger.md`.

1. Mechanical pass, from the repo root:

       bernstein-herdr ready --plan .agents/build/plans/<slug>.yaml

   Runs `.agents/skills/build-ready/templates/readiness.md` as commands: plan validate, root CLAUDE.md /
   AGENTS.md is a real file not a symlink, briefs present, disjoint ownership
   across siblings, spec citations resolve, Items / Validation / Report
   sections, 16k length cap, `context_files` present in the step base, and every
   Validation command executed on the base in a temporary worktree. Ends
   `READY` (exit 0) or `NOT READY` (exit 1). `--no-validate` skips only the
   base-worktree command runs. There is no `--help`; a bare `bernstein-herdr`
   prints the usage.
   Read the output, not just the verdict: `NOTE` lines are advisory (an
   allowlisted path that does not exist yet is a new file), a `RED` line is a
   brief error unless the brief names that red window, and `bernstein plan
   validate` warning about the unknown key `cli` on every step is expected.
   It runs the Validation block of every brief, judge briefs included; a judge
   brief that pastes the phase brief re-runs the phase's commands. Harmless.
2. Critic per brief: one fresh Opus subagent each, read-only, `model: opus`.
   Give it the brief path, the repo path, the spec and the files the brief
   names, and ask for blocking findings only: underspecified points, spec
   contradictions, items the stated Validation command cannot decide, paths the
   allowlist does not cover, and anything two briefs both claim. "Write no
   files, edit nothing." Save each answer to `<run>/readiness/critic-<T>.md`.
3. Edit briefs for blocking findings; rerun `bernstein-herdr ready` (it
   rewrites the pins over the edited briefs); rerun the critic; stop when a
   round warrants no edits. Two rounds is normal.
4. Permissions for the run:

       mkdir -p .claude
       cp .agents/skills/build-ready/templates/claude-settings.local.json .claude/settings.local.json

   Merge the allow lists by hand if the file already exists. It scopes the
   pipeline's allow rules and the auto-mode note to this build root only;
   nothing goes into user-global settings. The driver session must be started
   in the build root for it to apply, and subagents inherit it.
5. Record the round in `<run>/ledger.md` and offer `/build-run <run>`. The
   adapter refuses to start any step whose pins changed after this, so any
   later brief edit means rerunning this skill.

Never start executors from this skill.

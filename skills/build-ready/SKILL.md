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

   Runs `.agents/skills/build-ready/templates/readiness.md` as commands: plan
   validate, root CLAUDE.md / AGENTS.md is a real file not a symlink, briefs
   present, disjoint ownership across siblings, spec citations resolve, Items /
   Validation / Report sections, 16k length cap, `context_files` present in the
   step base, and every Validation command executed on the base in a temporary
   worktree. Two dispatch checks it also makes, because both fail silently at
   run time:

   - `~/.codex/config.toml` must set `model_reasoning_effort = "high"`. `codex
     exec` takes no effort flag, so that per-machine file outside the repo is
     the only lock; without it every codex step runs at the default effort.
   - every `role:` used in the plan must have a `role_model_policy` entry in
     `bernstein.yaml`. Role is the dispatch key: a per-step `cli:` is not in
     Bernstein's plan schema and was measured losing to the policy on the first
     retry, while a role with no entry falls back to the seed's top-level `cli:`.

   Ends `READY` (exit 0) or `NOT READY` (exit 1). `--no-validate` skips only the
   base-worktree command runs. There is no `--help`; a bare `bernstein-herdr`
   prints the usage.
   Read the output, not just the verdict: `NOTE` lines are advisory (an
   allowlisted path that does not exist yet is a new file) and a `RED` line is a
   brief error unless the brief names that red window.
   It runs the Validation block of every brief, judge briefs included; a judge
   brief that pastes the phase brief re-runs the phase's commands. Harmless.

   Briefs are TRACKED, at `.agents/build/plans/<slug>/<step>.md`, and the step's
   plan `description:` is what tells the agent to read one. That is the only
   channel: the sidecar never reaches Bernstein and the run directory is
   untracked and outside every worktree. A brief edit is a commit, and readiness
   re-pins over the committed file.
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
5. Record the round in `<run>/ledger.md` and offer `/build-run <run>`. Pins are
   written over the briefs as they stand now, so any later brief edit means
   committing it and rerunning this skill.

Never start executors from this skill.

---
name: build-ready
description: "Stage 3 of the build workflow: the readiness gate. Runs the mechanical checklist (plan validate, allowlists exist, same-stage allowlist overlap, validation commands green on the base, spec citations resolve, done-criteria present) and one fresh Opus critic per brief; edits briefs; converges when a critic round warrants no edits. Use on any plan before /build-run, including plans written by hand. Triggers: /build-ready, is the plan ready, check the briefs."
---

# build-ready

Input: `<run>` = `.agents/build/runs/<slug>`. Output: `<run>/readiness/ledger.md`,
`<run>/readiness/pins.json`, `<run>/readiness/critic-<T>.md`, briefs edited in
place, a line in `<run>/ledger.md`.

1. Mechanical pass, from the repo root:

       bernstein-herdr ready --plan .agents/build/plans/<slug>.yaml

   Runs `.agents/skills/build-ready/templates/readiness.md` as commands: plan
   validate, root CLAUDE.md / AGENTS.md is a real file not a symlink, briefs
   present, allowlist overlap between steps of the SAME stage, spec citations
   resolve, Items / Validation / Report sections, 16k length cap,
   `context_files` present in the step base, and every Validation command
   executed on the base in a temporary worktree.

   THE OVERLAP CHECK DOES NOT COVER SIBLINGS AS THIS WORKFLOW WRITES THEM. It
   compares steps within one stage only, and only each step's last glob against
   the last glob of each earlier step, by exact equality plus fnmatch
   containment. One step per stage means it never fires; two intersecting globs
   (`src/*/x`, `src/a/*`) would pass it anyway. Disjoint sibling ownership is
   the planner's guarantee, checked by reading the allowlists.

   Two dispatch checks it also makes, because both fail silently at run time:

   - `~/.codex/config.toml` must set `model_reasoning_effort = "high"`. `codex
     exec` takes no effort flag, so that per-machine file outside the repo is
     the only lock; without it every codex step runs at the default effort.
   - every `role:` used in the plan must have a `role_model_policy` entry in
     `bernstein.yaml`. Role is the dispatch key: a per-step `cli:` is not in
     Bernstein's plan schema and was measured losing to the policy on the first
     retry, while a role with no entry falls back to the seed's top-level `cli:`.
   - no step title or description may match Bernstein's L0 fast path
     (`lint`, `format`/`formatting`/`black`/`prettier`, `autofix`, `sort imports`/
     `isort`/`import order`, `rename X to Y` -- `core/quality/fast_path.py:108-125`,
     matched against `f"{title} {description}".lower()`). A match is never spawned:
     the task goes to `ruff`, which on a non-Python repo dies `Failed to spawn: ruff`
     and takes every dependent with it. Reword the title.
   - no two steps may share a `role:` with no dependency path between their stages.
     Bernstein batches concurrently open tasks by role into ONE spawn
     (`_groups_can_merge`, `tick_pipeline.py:113-127`), so a same-role parallel pair
     is one session, not two, and the DAG's parallel half is a fiction. Give one of
     them another `KNOWN_ROLES` name with its own policy entry (`ci-fixer` is the
     second codex role in the template for exactly this).
   - the repo must run NO git hook on commit. Linked worktrees share
     `.git/hooks`, so a repo-level `pre-commit` runs inside every agent worktree
     AND against Bernstein's salvage commit; when it failed there on 2026-09-03,
     14 files of finished work survived only as a patch under
     `.sdd/runtime/salvage/`, with no `salvage/*` branch to cherry-pick. An
     executable hook FAILS readiness. A hook-manager config (lefthook, husky,
     pre-commit) with no hook installed is a NOTE, because `lefthook install`
     puts them back at any moment -- a brief that told an executor to run the
     repo's `just setup` did exactly that mid-run and cost phase-2's 20 files.
     So: NEVER let a brief tell an executor to run a setup recipe that installs
     hooks, and once readiness is READY, before launching the run:

         mkdir -p .agents/build/nohooks
         git config core.hooksPath .agents/build/nohooks     # unset after the run

     `core.hooksPath` lives in untracked `.git/config`, so it never reaches an
     agent's diff, and unlike `LEFTHOOK=0`/`HUSKY=0` it survives both the
     adapters' filtered spawn env and a mid-run reinstall. Readiness accepts a
     configured empty hooks path as PASS, so re-running it after this is safe.
   - a `fix-N`/`polish-N` step's gate command must match the step it `fixes:`,
     and a `judge-N`'s the step it `judges:`. Readiness NOTEs a mismatch: the
     whole-tree `defaults.gate_cmd` is red by design once a later phase lands,
     and it blocked a correct fix three times (2026-09-03).

   Two things it now only WARNS about, printing `NOTE` and leaving the run READY:
   a brief with no `## Report` section (Codex skips the report file on roughly half
   its steps whatever the brief says; the gate records `report_present` per run
   instead), and an allowlisted path that does not exist yet. It also prints, per
   step, the gate command that step will run -- the sidecar's per-step `gate_cmd:`
   where it has one, else `defaults.gate_cmd`, else `just check`.

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

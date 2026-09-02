# build-workflow

A build pipeline for multi-phase software work driven by one Claude Code session
(the driver) with coding-agent executors (Claude Code, Codex, Antigravity CLI)
dispatched by [Bernstein](https://github.com/sipyourdrink-ltd/bernstein) into
git worktrees. Bernstein spawns its own adapters; this repo adds the readiness
gate, the scripted scorer, the blind-judge verdict, the run ledger, and the
templates and skills the driver works from.

## Quickstart

```
npx -y skills add git@github.com:tenequm/build-workflow.git -y \
  --skill build-design --skill build-plan --skill build-ready --skill build-run --skill build-close
git clone git@github.com:tenequm/build-workflow.git ~/pj/build-workflow   # skip if present
uv tool install bernstein --with ~/pj/build-workflow/bernstein_herdr
grep -q 'model_reasoning_effort = "high"' ~/.codex/config.toml \
  || echo 'model_reasoning_effort = "high"' >> ~/.codex/config.toml   # codex exec has no effort flag
git checkout -b build/<slug>                        # integration branch, never main
cp .agents/skills/build-run/templates/bernstein.yaml bernstein.yaml
sed -i "" "s|base_ref: .*|base_ref: build/<slug>|" bernstein.yaml
git add bernstein.yaml && git commit -m "chore: bernstein seed"   # must be committed
test -L CLAUDE.md -o -L AGENTS.md && echo "make it a real file first"
cp .agents/skills/build-ready/templates/claude-settings.local.json .claude/settings.local.json
```

Then, from a Claude Code session started in that root, with `docs/spec.md`
tracked: `/build-design`, `/build-plan .agents/build/runs/<slug>`, then
`/build-ready`, `/build-run`, `/build-close` on the same run directory.

Three parts:

- `skills/` - the driver-side stages, one skill each: design, plan, ready, run,
  close. Installed per project with `npx skills add
  git@github.com:tenequm/build-workflow.git --skill <name>`.
- `bernstein_herdr/` - a Python package installed once, INTO Bernstein's own
  environment (`uv tool install bernstein --with ./bernstein_herdr`); installed
  anywhere else its entry points are invisible to Bernstein. It provides the
  `bernstein-herdr` command: readiness, `run-config`, and `gate` -- the single
  quality gate Bernstein runs in each agent worktree before the merge, wired
  through `quality_gates.pipeline` with `command_override`. Executors are
  Bernstein's OWN adapters (`codex`, `claude`, `agy`), chosen per step by the
  step's `role:` and `role_model_policy` in `bernstein.yaml`. No fork of
  Bernstein, and no adapter of ours in the loop.
- `templates/` - the plan and its sidecar, `bernstein.yaml`, executor, judge and
  fix briefs, the judge prompt and the readiness checklist. The real files live
  in `skills/<stage>/templates/` so that `npx skills add` ships them; the
  top-level `templates/` entries are symlinks to those. `judge-prompt.md` is the
  one duplicated file: the package reads `templates/judge-prompt.md` at the repo
  root (judge.py:13), so a copy stays there. Keep the two in step.
- `docs/research/` - the research behind the design: eval results, tool
  survey, lab guidance, literature, patterns copied.

Repo layout the pipeline expects in a target project:

```
docs/spec.md                      the design contract, tracked, changes only via /build-design
.agents/build/plans/<slug>.yaml   Bernstein plan, tracked; <slug>.steps.yaml sidecar beside it
.agents/build/runs/<run>/         one run: briefs, contracts, readiness, reports, judge, shadow, runs.jsonl, ledger.md (untracked)
.sdd/                             Bernstein's own state
.worktrees/<step>/                one worktree per executor step
```

Design record and the evidence behind it: `docs/2609-02-design.md`.

Replaying a past phase to score an executor: clone the base branch out of
history, never `git worktree` it. A worktree shares the parent's object store,
so the merged answer stays reachable and the executor can reproduce it verbatim
(measured 2026-09-02). Use `git clone --single-branch --no-tags --branch
<base-branch> <src> <replay-root>` and `git remote remove origin`. Real builds
are unaffected.

The `bernstein-herdr` command the plan's completion signals call:

```
bernstein-herdr ready [--plan <yaml>]          readiness checks, codex effort, role policy, source pins
bernstein-herdr run-config                      run_config.json, run port, base_ref refusals, frozen base_sha
bernstein-herdr gate                            THE gate: Bernstein runs it in the agent worktree, pre-merge
bernstein-herdr scorer --step "<title>"         the scorer alone, by hand, in a worktree
bernstein-herdr judge-verdict --step "<title>"  the verdict alone, by hand, in a judge worktree
bernstein-herdr agy-session <db>                Antigravity session decoder
```

`gate` identifies its step from the worktree directory name (the agent_id) through
`.sdd/runtime/team.json` and `tasks.jsonl` -- the per-task CLAUDE.md that carries the
title is deleted before the gates run. Exit 1 is TERMINAL: no retry, no quarantine, the
branch goes to `salvage/<agent>` and a row lands in `.sdd/runtime/refused_merges.jsonl`.

`run-config` freezes the integration branch's sha at run start into
`<run>/bernstein.json` and the git ref `refs/build/base/<slug>`. The judge diffs that
ref, never the branch name: every merge advances the branch, so a judge that diffs the
branch after its dependency merged sees an empty diff and reviews nothing.

# build-workflow

A build pipeline for multi-phase software work driven by one Claude Code session
(the driver) with coding-agent executors (Claude Code, Codex, Antigravity CLI)
dispatched by [Bernstein](https://github.com/sipyourdrink-ltd/bernstein) into
git worktrees, each visible as a [herdr](https://herdr.dev) pane.

## Quickstart

```
npx -y skills add git@github.com:tenequm/build-workflow.git -y \
  --skill build-design --skill build-plan --skill build-ready --skill build-run --skill build-close
git clone git@github.com:tenequm/build-workflow.git ~/pj/build-workflow   # skip if present
uv tool install bernstein --with ~/pj/build-workflow/bernstein_herdr
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
  anywhere else its entry points are invisible to Bernstein. Registers the herdr executor adapters
  (`herdr-claude`, `herdr-codex`, `herdr-agy`, and `herdr-fake` -- a shell
  script in the pane, for testing the chain without a model) and the two gates
  (`scorer`, `blind_judge`) through Bernstein's entry-point groups. No fork of Bernstein.
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
bernstein-herdr ready [--plan <yaml>]          readiness checks and source pins
bernstein-herdr run-config                      run_config.json, run port, stale-server/stale-orchestrator and base_ref refusals
bernstein-herdr scorer --step "<title>"         scripted gate, run in the worktree
bernstein-herdr judge-verdict --step "<title>"  completion signal of a judge step
bernstein-herdr agy-session <db>                Antigravity session decoder
```

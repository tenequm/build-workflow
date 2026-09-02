# build-workflow

A build pipeline for multi-phase software work driven by one Claude Code session
(the driver) with coding-agent executors (Claude Code, Codex, Antigravity CLI)
dispatched by [Bernstein](https://github.com/sipyourdrink-ltd/bernstein) into
git worktrees, each visible as a [herdr](https://herdr.dev) pane.

Three parts:

- `skills/` - the driver-side stages, one skill each: design, plan, ready, run,
  close. Installed per project with `npx skills add
  git@github.com:tenequm/build-workflow.git --skill <name>`.
- `bernstein_herdr/` - a Python package installed once (`uv tool install
  ./bernstein_herdr` or `pipx`). Registers the herdr executor adapters
  (`herdr-claude`, `herdr-codex`, `herdr-agy`) and the two gates (`scorer`,
  `blind_judge`) through Bernstein's entry-point groups. No fork of Bernstein.
- `templates/` - plan and its sidecar, `bernstein.yaml`, executor, judge and fix
  briefs, the judge prompt and the readiness checklist the skills instantiate
  into a repo's `.agents/build/`.
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

The `bernstein-herdr` command the plan's completion signals call:

```
bernstein-herdr ready [--plan <yaml>]          readiness checks and source pins
bernstein-herdr scorer --step "<title>"         scripted gate, run in the worktree
bernstein-herdr judge-verdict --step "<title>"  completion signal of a judge step
bernstein-herdr agy-session <db>                Antigravity session decoder
```

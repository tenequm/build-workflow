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
- `templates/` - the plan, brief, judge prompt and readiness checklist the
  skills instantiate into a repo's `.agents/build/`.

Repo layout the pipeline expects in a target project:

```
docs/spec.md                      the design contract, tracked, changes only via /build-design
.agents/build/plans/<slug>.yaml   Bernstein plans, tracked
.agents/build/runs/<run>/         one run: briefs, contracts, readiness, reports, judge, shadow, runs.jsonl, ledger.md (untracked)
.sdd/                             Bernstein's own state
.worktrees/<step>/                one worktree per executor step
```

Design record and the evidence behind it: `docs/2609-02-design.md`.

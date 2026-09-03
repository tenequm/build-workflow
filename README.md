# build-workflow

A three-stage pipeline for multi-phase software work. One driver plans,
supervises, validates, and lands the build. Bernstein dispatches coding-agent
executors into git worktrees. The driver never edits application code.

This repo supplies the driver skills, readiness checks, scripted scorer, blind
judge contract, run ledger, and generated-plan templates.

## Quickstart

```sh
npx -y skills add git@github.com:tenequm/build-workflow.git -y \
  --skill build-plan --skill build-run --skill build-close

git clone git@github.com:tenequm/bernstein.git ~/pjv/sipyourdrink-ltd/bernstein
git -C ~/pjv/sipyourdrink-ltd/bernstein checkout fix/warm-pool-empty-worktree
uv cache clean bernstein
uv tool install ~/pjv/sipyourdrink-ltd/bernstein \
  --with ~/pj/build-workflow/bernstein_herdr --force --reinstall
# NEVER install Bernstein from PyPI for this workflow.

grep -q 'model_reasoning_effort = "high"' ~/.codex/config.toml \
  || echo 'model_reasoning_effort = "high"' >> ~/.codex/config.toml
```

## Pipeline

1. `/build-plan` - design -> cut -> workspace -> ready. Accept an idea, an
   existing plan document path, or nothing. Discover repo conventions, write
   the plan document, generate machine artifacts and briefs, create the
   workspace, run readiness, and end stopped.
2. `/build-run <path_to_plan_doc>` - execute the DAG, polish and blind-judge the
   whole branch, dispatch fixes, run the whole-tree gate, end local, and ask
   whether to open a PR.
3. `/build-close <path_to_plan_doc>` - land through an approved PR or local
   merge, run discovered release ceremonies, preserve evidence, and clean up.

Starting `/build-run` is an explicit paid decision. Opening a PR and merging
both require explicit user consent.

## What runs where

| Piece | Process | Where it runs | Model |
|---|---|---|---|
| driver | your agent session | `.claude/worktrees/<slug>` on `<type>/<slug>` | the model you drive with; it never edits application code |
| readiness, run config | `bernstein-herdr ready` / `run-config` | the workspace root, before execution | none |
| orchestrator | `bernstein run --port N` | the workspace root, backgrounded | none |
| executor, role `resolver` | `codex exec` spawned by Bernstein | `.sdd/worktrees/resolver-<id>/`, branch `agent/resolver-<id>` | `gpt-5.6-sol`, effort from `~/.codex/config.toml` |
| executor, role `ci-fixer` | `codex exec` spawned by Bernstein | its own worktree and `agent/...` branch; a second Codex role keeps parallel tasks separate | `gpt-5.6-sol`, same config |
| executor, role `analyst` | `claude -p` spawned by Bernstein | its own worktree and `agent/...` branch | `claude-opus-5`, high effort |
| judge, role `adversary` | `claude -p` spawned by Bernstein | a worktree branched from the workspace branch after the phase merged | `claude-opus-5`, high effort |
| whole-branch judge | a fresh driver subagent | detached from `refs/build/base/<slug>` with the branch diff applied | the driver's own model |
| gate | `bernstein-herdr gate` | inside each step worktree, before merge | none |

Roles, not per-step `cli:`, are the dispatch key. The names avoid Bernstein's
catalog personas; see the comments in `bernstein.yaml` and
`docs/2609-02-persona-prefix.md`.

## Constraints

1. One ACTIVE plan per checkout. `.sdd/`, the task-server port, run config,
   ACTIVE, and `refs/build/base/<slug>` are per checkout. A concurrent build
   needs another workspace.
2. Bernstein must be the patched clone below, not stock upstream. Two fixes
   this workflow depends on are carried there: worktree isolation no longer
   refuses a symlink that stays inside its own worktree, and a per-spawn task
   instruction file replaces a symlinked `CLAUDE.md` instead of writing through
   it. Without them a repo that tracks `CLAUDE.md -> AGENTS.md` fails every
   spawn, and the orchestrator's write lands on a tracked file.

## Components

- `skills/` contains the three driver skills: plan, run, and close. Install
  them per project with `npx skills add`.
- `bernstein_herdr/` is installed into Bernstein's environment with
  `uv tool install <patched clone> --with ./bernstein_herdr`. It provides
  readiness, run config, and the pre-merge quality gate. Executors remain
  Bernstein's own adapters.
- `docs/research/` contains the eval, tool-survey, and design evidence.

## Target repo layout

```text
<plans_dir>/<date>-<slug>.md       plan document, tracked; directory discovered from repo instructions
.agents/build/plans/              generated machine artifacts plus ACTIVE, tracked
.agents/build/plans/<slug>.yaml   Bernstein plan; sidecar beside it
.agents/build/plans/<slug>/       tracked executor and judge briefs
.agents/build/runs/<slug>/        untracked evidence, contracts, reports, ledger, handoff
.claude/worktrees/<slug>/         workspace on <type>/<slug>
.sdd/                             Bernstein runtime and executor worktrees
```

The sidecar pins the plan document as `defaults.doc`, the optional product spec
as `defaults.design`, and the repo's whole-tree command as `defaults.gate_cmd`.

## Commands

```text
bernstein-herdr ready [--plan <yaml>]          readiness, citations, dispatch, and source pins
bernstein-herdr run-config [--plan <yaml>]     run config, port, base checks, and frozen base sha
bernstein-herdr gate                           pre-merge gate in the executor worktree
bernstein-herdr scorer --step "<title>"         scorer alone in a worktree
bernstein-herdr judge-verdict --step "<title>"  verdict alone in a judge worktree
```

`gate` identifies a step from the worktree agent id through
`.sdd/runtime/team.json` and `tasks.jsonl`. Exit 1 refuses that merge. The
refused branch survives under `refs/graveyard/<sid>-<ts>` with a bundle under
`.sdd/graveyard/`, and the attempt lands in `refused_merges.jsonl`. A lifecycle
retry may already be scheduled, so the board and spawner log decide whether the
task is terminal.

The gate always measures the sidecar command. Its extra deleted-test,
suppression, and lint heuristics are Go- and TypeScript-shaped; Python and Rust
plans must put equivalent guarantees in `defaults.gate_cmd`. When the sidecar
sets no command, the fallback is `just check`; pin the repo's real check
instead.

`run-config` freezes the workspace branch sha into `<run>/bernstein.json` and
`refs/build/base/<slug>`. Judges diff the frozen ref, never the moving branch.

## Replay isolation

Replay a past phase from a clone, never a worktree. A worktree shares the
parent's object store, so a historical answer can remain reachable and make the
replay invalid.

```sh
git clone --single-branch --no-tags --branch <base-branch> <src> <replay-root>
git -C <replay-root> remote remove origin
```

Real builds run forward from a base that has no answer in the repository and
use Bernstein worktrees normally.

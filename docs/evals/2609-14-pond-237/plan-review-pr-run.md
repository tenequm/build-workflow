# Plan: the `/review-pr` run on pond#237

Reviewer C of three. See [the comparison index](README.md).

This document is self-sufficient on purpose: it is the source of truth for
executing the run, and it is written to be picked up cold, after a context
compaction, with nothing else loaded.

## Why the lane changes

The lane that was proven on 2026-09-12 was `claude-sonnet-5` as manager over
five free local qwen lenses. It worked: the smoke case recovered in 1205s, and a
real review of a 7-file governance PR recovered 11 of 14 hand findings.

Two things force a change now:

1. **Claude Max is at about 10% of the weekly quota.** The lane cannot lean on
   Claude for the reasoning-heavy half.
2. **codex limits are refreshed**, and `gpt-5.6-sol` at high effort has just
   produced [baseline B](baseline-polish-codex-5.6-sol-high.md) on this exact
   pull request, including the one blocking finding opus-5 missed. It has earned
   the judgment seat.

So the reasoning half moves to codex, the cheap half stays on the free local
gateway, and the two cheapest lenses get **shadowed** so this run also answers a
second question: can the free half stay free?

## Role is a model slot

Routing in bernstein is per **role**, not per task. The lens lives in the task
text; the role only decides which model executes it. Three tasks carrying the
same prompt under three different roles therefore run on three models, which is
why six shadow tasks need only three role entries.

`bernstein.core.plan_schema.KNOWN_ROLES` has 19 entries: `adversary`, `analyst`,
`architect`, `backend`, `ci-fixer`, `data`, `devops`, `docs`, `frontend`,
`manager`, `ml-engineer`, `prompt-engineer`, `qa`, `resolver`, `retrieval`,
`reviewer`, `security`, `visionary`, `vp`.

## The lane

| Step | Role | Model | Counted in report? |
|---|---|---|---|
| Plan, create tasks | `manager` | codex `gpt-5.6-sol` (high) | - |
| Lens 1: claim vs implementation | `analyst` | codex `gpt-5.6-sol` | yes |
| Lens 2: side-effect gating | `security` | codex `gpt-5.6-sol` | yes |
| Lens 3: design and reuse | `analyst` | codex `gpt-5.6-sol` | yes |
| Lens 4: efficiency | `qa` | local qwen `flash-next` | yes |
| Lens 4: efficiency | `data` | agy `gemini-3.7-flash-medium` | **shadow** |
| Lens 4: efficiency | `retrieval` | `claude-sonnet-5` | **shadow** |
| Lens 5: cleanliness | `qa` | local qwen `flash-next` | yes |
| Lens 5: cleanliness | `data` | agy `gemini-3.7-flash-medium` | **shadow** |
| Lens 5: cleanliness | `retrieval` | `claude-sonnet-5` | **shadow** |
| Write the report | `reviewer` | codex `gpt-5.6-sol` | yes |

11 agents: 5 codex, 2 qwen, 2 gemini, 2 sonnet.

**The shadow design is symmetric by design.** Lens 4 and lens 5 each run the
*identical* task text on three models in parallel. Nothing about the prompt
differs; only the executing model does. That is the whole point - any difference
in output is attributable to the model and to nothing else.

Shadows write `shadow-<model>-<lens>.md` into the run's scratch directory. The
goal text must tell the report writer to **ignore every `shadow-*` file**, so
shadows cost nothing in the review output and remain on disk for the diff
afterwards.

Lenses 1-3 are the expensive, judgment-heavy ones and are not shadowed:
shadowing the strongest step teaches nothing actionable, while shadowing the free
lenses answers a question with a decision attached to it.

## Steps

1. **Seed edit** - `skills/review-pr/templates/review-seed.yaml`: the seven role
   entries above under `role_model_policy`. Nothing else changes.
2. **Goal edit** - `skills/review-pr/templates/review-goal.md`: assign a role per
   lens, name the three parallel tasks for lens 4 and for lens 5, and add the
   `shadow-*` exclusion rule for the report writer.
3. **Proof: all four corpus cases.** The goal text changed, and the standing rule
   in `CLAUDE.md` is that a goal-text change re-runs the full set.
   `just eval --jobs 2`, about 40 minutes unattended. **No shadows in the proof** -
   it is a plumbing test, not a model comparison. Temporarily route
   `data`/`retrieval` to qwen for it, or omit those tasks from the proof goal.
4. **Run pond#237** per `skills/review-pr/SKILL.md`: throwaway checkout at the PR
   base, the two `gh` reads first, then `git remote remove origin`, then the PATH
   shims, then `bernstein run`. Expect 60-90 minutes.
5. **Compare four ways** and write up recovered / missed / novel into
   `comparison.md` beside this file.

## Grading rules

Fixed in [the index](README.md) before the run so the bar cannot move afterwards.
The short form: compare by substance not by line anchor; score recovered /
missed / novel against the union of A and B; **the Pi `sqlite_path` blocking
finding is the single most important cell**; novel findings are judged true /
false / unfalsifiable and a false one costs more than a missed cleanliness item;
every miss the operator would have acted on becomes a new corpus case.

## Facts that cost time to learn

Do not re-derive these.

- **Codex effort is not a flag.** `codex exec` reads `model_reasoning_effort`
  from `~/.codex/config.toml`, which on this host already holds
  `model = "gpt-5.6-sol"` and `model_reasoning_effort = "high"`. The bernstein
  codex adapter having no effort code is by design. This repository's own
  readiness check documents it at
  `bernstein_herdr/src/bernstein_herdr/ready.py:222-232` and hard-fails a run
  when it is missing.
- **The PATH shims cover `pi` and `claude` only.** `codex` and `agy` are
  unshimmed and read the reviewed tree's own config (`.codex/`, `.agy/`,
  `AGENTS.md`). pond is the operator's own repository, so this lane is safe here
  and is **not** reusable on a third-party repository until a codex shim exists.
- **The local gateway has three models, all 262144 context**: `qwen3.8-flash-next`
  at 209 tok/s (the fastest available - there is nothing quicker to switch to),
  `qwen3.8-27b-nvfp4` at 78 tok/s (dense, stronger per token),
  `qwen3.6-35b-a3b-nvfp4` at 54 tok/s. Never read or print the API key in
  `~/.pi/agent/models.json`.
- **Do not raise `--jobs` past 2** on the local lane: four in flight drew 429s on
  36 of 67 sessions.
- **A worker's uncommitted files do not cross the worktree boundary**, and
  `bernstein memory` facts are worktree-scoped and die with the worktree. The only
  channel that crosses is one scratch directory outside every repository,
  `mktemp -d` by the lead before any task is created and quoted verbatim in every
  worker's task text.
- **The report has exactly one correct location**: the checkout the run started
  in, which from inside a worktree is `$(dirname "$(git rev-parse --git-common-dir)")`
  and is the same command in the checkout itself.
- **Never attach a working-tree acceptance check** (`git status` empty, N entries).
  The orchestrator keeps runtime state inside the checkout, so such a check fails
  every worker forever and destroys the report it was meant to protect.
- **The engine pushes on its own**: `git push origin` on every agent merge and on
  salvage. Stripping the remote is the countermeasure, and it is why
  `git remote remove origin` is in the invocation.
- **Residual, unfixed**: the engine cannot observe a pi agent's liveness (pi
  writes nothing to a redirected stdout until its turn ends), so it judges working
  agents dead. Four to seven tasks fail and retry per run. This costs wall clock,
  not the deliverable. **Do not treat "zero failed tasks" as a pass bar.**
- **A run ends only at a `/proc` cwd sweep**: `harness.sweep(pathlib.Path(dir))`
  (a `Path`, not a `str`). The CLI returning means nothing.
- **Launch long runs `setsid`-detached** (`setsid nohup ... & disown`); the
  harness's background-task supervisor kills them when the host hits a transient
  low-memory spike.

## The standing bar

Unchanged by this plan. The smoke case (`just eval case-01-off-by-one`, about 20
minutes) after any engine, seed or host change; all four cases only when the goal
text changes. Every run appends one row to `docs/review-ledger/evals.jsonl`; rows
carrying `"corpus": "v2"` are the comparable ones.

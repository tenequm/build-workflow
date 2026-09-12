# build-workflow - agent instructions

After meaningful skill or template edits, release with `just ship`, not a bare
`git push`. Plugin consumers only receive updates when the manifest version
changes; `ship` bumps both `plugin.json` files in sync, commits, and pushes.
Doc-only or internal changes may push without shipping.

The operator's own machines consume `skills/` via live symlinks from
`~/.claude/skills` (the `bwup` shell function), so local edits are live
immediately and need no install step.

A build occupies only its workspace branch: the plan commits nothing to the
primary (workspace-at-first-write, 2026-09-04; rationale in
[the decision record](docs/knowledge/decisions/workspace-at-first-write.md)),
so other sessions may work on main freely while a build runs; primary drift
is resolved by /build-close's merge. The one shared file is the primary's `.claude/settings.local.json`,
written once at workspace creation.

The four skills are self-contained: a skill never invokes another skill
or slash command and never reads a file from a sibling skill's directory. Each skill carries its own
`templates/`; a template two skills need is copied into both. Consumers
install the skills one at a time, and a skill that reaches outside itself
breaks for them. `scripts/skill_isolation.py` enforces this (pre-commit); shared
Python is vendored by `bernstein_operator/scripts/sync-skill-code.py`, whose
`--check` requires the copies to stay byte-identical (build-plan is the only skill
that vendors any).

`/review-pr` reviews someone else's pull request and owns no orchestrator: it hands
one free-text review goal (`skills/review-pr/templates/review-goal.md`) and a model
seed (`templates/review-seed.yaml`) to a stock `bernstein run` inside a checkout of
the target repository, then reads back `review-report.md`. The skill ships no Python.

The fence is public repositories and this repository's eval corpus only, with no
GitHub token in play: the two `gh` commands that fetch the diff and the pull request
body run before the engine starts, and no model session is ever handed a token. Two
lanes exist. The local-first lane routes every role through the `pi` CLI against a
local LiteLLM gateway - `litellm/qwen3.8-flash-next`, `litellm/qwen3.8-27b-nvfp4`,
`litellm/qwen3.6-35b-a3b-nvfp4` - which costs nothing, has no rate limits, and keeps
prompts on the machine. The quality lane is subscription-backed: a `claude-sonnet-5`
manager over `agy gemini-3.7-flash-medium` workers. The other load-bearing rule is
that any validation, lint or test command a reviewing agent runs is read from the
BASE branch and never from the pull request's own tree. That rule, and never-commit,
live as constraints in `review-seed.yaml` and in the goal text - they survive only
there, so weaken them there or not at all.

Two rules apply to anything added to it:

- Cost figures are observability, never control flow: no new bound may read a dollar
  amount. The dollar-reading ceilings inside /build-run's judge ceremony are the
  deliberate, non-extensible exception
  ([why](docs/knowledge/decisions/cost-is-observability-never-control-flow.md)).
- A change is proven against the frozen corpus in `fixtures/review-pr-cases/` before it
  is believed, and the size of the proof follows what changed: an engine, seed or host
  change re-runs the smoke case alone (`just eval case-01-off-by-one`, ~30 min, passes
  only as RECOVERED with zero failed tasks and a clean sweep); a change to the goal text
  runs all four (`just eval`). Each invocation appends one row to
  `docs/review-ledger/evals.jsonl`. There is no test suite for /review-pr; that ledger is
  the regression signal.

A retro item closes only as a check, a template field, or a test - never as
another skill sentence.

Durable project knowledge lives in `docs/knowledge/` (an OKF bundle; read its
`index.md` first). Load the okf-project-knowledge-base skill before reading or
writing it, and after substantial work review whether a durable decision or
finding should be captured there. The index listing is generated: after any
concept change run `python3 scripts/kb_index.py` (pre-commit enforces
`--check`). There is no update log - git history is the log.

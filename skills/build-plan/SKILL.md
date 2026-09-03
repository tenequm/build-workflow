---
name: build-plan
description: "Design, cut, workspace, and ready a three-stage Bernstein build. Use /build-plan with an idea, an existing plan document path, or nothing whenever a build needs a plan, generated DAG artifacts, an isolated workspace, and readiness validation before paid execution."
---

# build-plan

Run in the primary checkout. Accept an idea, an existing plan document path, or
nothing. Never edit application code. Research and criticism may use subagents;
the driver writes every plan document, generated plan, contract, and brief.

Use absolute paths in commands. Use `fd`, not `find`, and `rg` without `-r`.
Author ASCII only with a single `-`, never an em dash.

The moment a skill instruction proves wrong, ambiguous, or is deviated
from - or the user has to intervene where the skill should have sufficed -
append `- workflow: <what and why>` to `<run>/ledger.md`. These lines are
the retro's input for improving the workflow after the run.

## 1. DESIGN

Discover repo facts before designing. Check CLAUDE.md (or the equivalent
project instructions) for the product spec document - commonly `docs/spec.md`
or `DESIGN.md`. A repo may have none; if none is documented, ask. Check the
same instructions for the plan-documents directory - commonly `docs/plans/`.
If none is documented, use `docs/plans/`. Check them for the whole-tree check
command - commonly `just check`, `pnpm check`, `cargo clippy`, or
`uv run ruff check`. If none is documented, ask.

Read the relevant code, prior plan documents, and handoffs. Fan out subagents
for RESEARCH ONLY: identify uncertainties, find dependencies and their docs,
and verify assumptions against the codebase. Research subagents may use
`model: opus`. Require reports only; never let a subagent write the document.

When starting from an idea, ask the user three to five questions that change
the design. Record each decision and rejected alternative. Pick a short
lowercase title slug, one word or two joined by `-`, and write the tracked plan
document at `<plans_dir>/<YYMM-DD>-<slug>.md`. When given an existing design
document, edit it IN PLACE as the plan document and skip the interview. With no
argument, continue the current document when it is clear; otherwise ask.

Write these sections in order:

1. Numbered design sections named `## <n>. <title>`. Once a brief cites a
   section, freeze its number and meaning.
2. `## Phases`, with a table whose every row names an owner. Use an executor
   role for code-in-worktree work. Use `user` for live credentials, infra ops,
   or manual verification. Never cut `owner: user` rows into the DAG; hand them
   back at close.
3. `## Spec amendments`, listing exactly which product-spec sections this
   build adds or amends. Executors make those changes inside their allowlists;
   the driver does not. Omit this section when the repo has no product spec.
4. Optional `## Release requirements`, for `/build-close`.

Validate with one fresh critic subagent on your own model. Keep it read-only.
Give it the whole document and touched code and ask: "contradictions, undefined
terms, invariants with no check, uncut dependencies; blocking findings only;
write no files". Edit the document yourself and rerun fresh critics until a
round warrants no edits. Commit the plan document with a conventional commit.

For an old plan, skip DESIGN when its pinned document hash is current or the
user says the document is current.

## 2. CUT

Pick `<slug>` here. It is the run directory name, machine plan `name:`, and
machine plan file name. Use the title-slug rule for every `<T>`: lowercase,
replace each non-alphanumeric run with `-`, trim, and cut to 48 characters.

Produce exactly:

    .agents/build/plans/<slug>.yaml
    .agents/build/plans/<slug>.steps.yaml
    .agents/build/plans/<slug>/<step>.md
    .agents/build/runs/<slug>/contracts/<seam>.md

Keep only generated machine artifacts plus `ACTIVE` under
`.agents/build/plans/`. Keep prose in `<plans_dir>`. Keep evidence and
driver-written seam contracts in `<run> = .agents/build/runs/<slug>/`.

Briefs are tracked, not run files. Only tracked files enter executor worktrees.
Point each plan `description:` at its tracked brief. A sidecar `brief:` starting
with `.agents/` resolves from the repo root; other paths resolve from `<run>`.
A brief edit is a commit.

Copy templates from `.agents/skills/build-plan/templates` for a project install
or `~/.agents/skills/build-plan/templates` for a global install. Write the
machine plan from `build.yaml`, the sidecar from `build.steps.yaml`, executor
briefs from `brief.md`, judge briefs from `judge-brief.md` plus
`judge-prompt.md`, and fixes from `fix-brief.md`. Replace every placeholder and
remove unused sibling, judge, fix, and polish stanzas.

Pin discovery in the sidecar:

    defaults.doc: <plan document path>
    defaults.design: <product spec path>  # omit when none
    defaults.gate_cmd: <whole-tree check command>

Decompose by dependency graph, not file list. Target 15-30 minutes of executor
wall per step. Write a driver-owned interface contract before a seam split.
Split more than about eight files or two independent packages into disjoint
`phase-Na`, `phase-Nb` siblings. Give shared files to one sibling or a small
predecessor. Readiness compares only same-stage last globs and is not a real
intersection test, so guarantee sibling disjointness yourself.

Use one step per stage and make stage name equal step name. Carry the DAG in
`depends_on`. Bernstein batches concurrently open tasks with the same role into
one session. Give parallel siblings different roles that resolve to different
dispatch policies. Never write per-step `cli:`; Bernstein loses it on retry.
Use only the persona-free roles: `resolver` and `ci-fixer` for Codex,
`analyst` for Claude, and `adversary` for judges. Assign seam and investigation
work to `analyst`; assign transfer, exact-line, and fix work to `resolver` or
`ci-fixer`.

Set every step's `scope:` because it controls the adapter watchdog: `small`
15m, `medium` 30m, `large` 60m, and `large` plus `complexity: high` 120m.
Default is medium. Use large above about 20 minutes and for every multi-file
judge.

Use this judge shape:

- Make `judge-N` depend on every phase-N sibling.
- Make `fix-N` depend on `judge-N`; it always runs and takes the no-op path only
  for a legal verdict with both counts declared and `Certain: 0`.
- Let phase N+1 depend on phase N, not its judge, when speculation is safe.
- Set judge sidecar `judges:` to the exact reviewed title, `report:` exactly
  `.agents/blind-review.md`, and plan `files: []`.
- Set every fix or polish sidecar `fixes:` to the exact repaired title and copy
  that step's own scoped `gate_cmd:`.

`fix-N` and phase N+1 commonly overlap. Either serialize phase N+1 behind
`fix-N`, or keep them concurrent and add a final regression step depending on
both with the whole-tree gate. Record the choice in a plan comment. Never make
the fix depend on the later consumer; that verifies the consumer before the
repair lands.

For every executor brief:

- Cite plan sections only as literal `PLAN <n>` or `PLAN <n.m>` tokens.
- Cite product-spec sections only as `DESIGN <n>` and only when a product spec
  exists.
- Include `## Items`, `## Validation` with a fenced command block, and
  `## Report` naming Deviations.
- Give each item a done criterion that Validation can decide.
- List exact allowlisted paths and exact validation commands.
- Keep it under 16k.
- Never tell an executor to run a setup recipe such as `just setup`,
  `make bootstrap`, or `lefthook install`; linked worktrees share hooks.
- Choose a writable, committed report path and set sidecar `brief:` and
  `report:` explicitly. If `.agents/` is refused, use a tracked allowed path.

Set sidecar `defaults.base` to the future `<type>/<slug>` workspace branch.
Set a step-specific gate when the whole tree is intentionally red. The scorer
measures the command even where its Go and TypeScript heuristics do not apply.

Record hashes in `<run>/ledger.md` and commit `.agents/build/plans` with a
conventional commit. Re-cut only changed artifacts when re-verifying an old
plan.

## 3. WORKSPACE

Make this phase idempotent. Resolve checkout identity first with
`git rev-parse --git-dir`, `git rev-parse --git-common-dir`, and
`git rev-parse --show-superproject-working-tree`. Refuse a submodule. When the
git dir differs from the common dir and the superproject result is empty,
already inside a linked worktree: continue to READY.

In the primary checkout, if `<run>/workspace.json` exists, verify its five
fields and re-enter its recorded absolute `path` with the native EnterWorktree
tool in path mode. Never create a second worktree.

Otherwise capture the primary HEAD sha and branch. Ask once for branch type
`feat|fix|chore|refactor`, default `feat`. Ensure `.claude/worktrees/` is
gitignored, adding only that line when needed. Create:

    git worktree add -b <type>/<slug> <primary>/.claude/worktrees/<slug> <primary HEAD sha>

Use absolute paths in the real command. Copy ONLY the untracked run directory:

    rsync -a <primary>/<run>/ <workspace>/.agents/build/runs/<slug>/

Bootstrap: anything the repo tracks (skills, lock, symlinks) arrives via the
branch. Copy into the workspace, never committing, only the gitignored local
state the templates need: `.agents/skills/` and `skills-lock.json` when
untracked (template paths must resolve from the workspace root).

Permissions live in the PRIMARY checkout, not the workspace: Claude Code reads
`.claude/settings*.json` from the main checkout's root for every worktree of
the repo, and a worktree's own settings file is ignored. Copy
`.agents/skills/build-plan/templates/claude-settings.local.json` to
`<primary>/.claude/settings.local.json`, merging allow lists by hand if the
file exists, and confirm the primary gitignores it. Config reloads on the
worktree switch, so no session restart is needed.

Copy the build-run `bernstein.yaml` template when the repo has none and set
`quality_gates.base_ref: <type>/<slug>`. If the repo tracks one, change only
`base_ref`. Write `.agents/build/plans/ACTIVE` as one line containing
`<slug>.yaml`. Write `<run>/workspace.json` with EXACTLY these five fields:
`path`, `branch`, `base`, `base_branch`, `primary`.

Make one seed commit containing ONLY `bernstein.yaml`, the `.gitignore` edit
when made, and `ACTIVE`. Keep copied local state untracked. Enter the workspace
with native EnterWorktree path mode. If EnterWorktree is absent, tell the user
to start a session in the absolute workspace path and stop.

## 4. READY

From the workspace root run:

    bernstein-herdr ready --plan .agents/build/plans/<slug>.yaml

Read every PASS, FAIL, RED, and NOTE line. NOTE is advisory: a missing
allowlisted path may be a new file and a missing report requirement weakens
evidence. Treat unexpected RED as a brief error unless the brief names that red
window. Read every printed gate command and replace the `just check` fallback
with the discovered whole-tree command. Keep step-specific gates scoped.

If commit hooks exist, follow the printed remedy: point `core.hooksPath` at an
empty repo-local directory and rerun readiness. Preserve the dispatch guards:
Codex effort must be high, every role needs a `role_model_policy`, fast-path
titles must be reworded, parallel tasks must not share a role, judge fields must
be exact, and fix gates must match the step they repair.

Run one fresh critic subagent per brief on your own model, read-only. Give each
the brief, plan document, optional product spec, and named files. Ask for
blocking findings only: underspecification, contradictions, validation gaps,
allowlist gaps, and overlapping claims. Require "write no files". Edit briefs
yourself, rerun ready so it re-pins, and rerun fresh critics until a whole round
warrants no edits.

Record the readiness rounds and final pins in `<run>/ledger.md`. End STOPPED.
Print exactly:

    use /build-run <path_to_plan_doc> to start plan execution

Never auto-chain. Starting the paid run is the user's explicit decision.

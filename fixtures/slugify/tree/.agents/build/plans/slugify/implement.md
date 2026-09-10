# Brief: implement - add textkit.slugify

You are an executor in a git worktree of your own, on your own `agent/...`
branch. Read this whole file, then the spec sections cited below as the literal
token `SPEC <n>` (the build spec, sidecar `defaults.spec`) and the plan
sections cited as `PLAN <n>` / `PLAN <n.m>` (sidecar `defaults.doc`). Read
product-spec sections cited as `DESIGN <n>` only when the sidecar pins a
product spec. These are the only forms readiness resolves. Where this brief
names witness tests and contract files by path, those files are the
specification: do not reinterpret them from prose. Then read the machine plan
`.agents/build/plans/slugify.yaml` (this step). Do the work, write the report,
then COMMIT on your branch: the commit is how the work reaches the gate and the
merge, and nothing runs after you exit. Do not ask questions; where something is
ambiguous, build the smallest faithful shape and record it under "Deviations".

## Context

textkit has `word_count` only (textkit/__init__.py). Nothing is expected red.
Implement SPEC 2 outcomes 1 and 2 using the approach in SPEC 3; PLAN 8 fixes the test location.

## Items

0. Write and COMMIT `reports/implement.md` with a line beginning exactly
   `Validation:` naming the command, its exit code and result. The step does not
   complete without that committed file; create `reports/` if absent.

1. `textkit/slug.py` defines `slugify(text: str) -> str` per SPEC 2 outcomes 1-2 and SPEC 3. Done when the Validation command passes.
2. `textkit/__init__.py` exports `slugify` so `from textkit import slugify` works, keeping `word_count`.
3. `tests/test_slug.py` asserts both SPEC 2 examples ("Hello, World!" -> "hello-world", "  --A  b--  " -> "a-b") and that text with no letters or digits gives "".

## File allowlist

`textkit/slug.py`, `textkit/__init__.py`, `tests/test_slug.py`, plus your report file `reports/implement.md`. The report path is not part of
the allowlist and never counts as a violation. Stop and report instead of
editing any other path.

Two facts about `.agents/`, where this brief and usually the report live: many
repos GITIGNORE it, so `git add <report>` stages nothing and you need
`git add -f`; and some sandboxes refuse writes under it altogether. If your
report path is refused, say so in the FIRST line of your final message and name
the path -- do not paste the report there instead and treat the step as done.
Nothing reads a final message: the gate archives and scores the COMMITTED file,
and a step that commits nothing blocks.

## Validation (exactly, from the worktree root)

```
python3 -m unittest discover -s tests -q
```

Report each command, its exit code and the last 30 lines of output.

## Rules

- The plan directory (spec.md, plan.md, facts.md, report.md) is driver-owned: never edit it.
- Edit the product spec only when the plan's Spec amendments section requires
  it and the file is in this step's allowlist.
- ASCII only in authored text. No em-dashes.
- Commit on your branch with a conventional message. Never push. Never main.

## Report

Write `reports/implement.md` in the worktree root: per item DONE / DEVIATED / SKIPPED
with file:line; a line beginning exactly `Validation:` for each command with its exit code; Deviations (with the alternative
rejected and why); Open (walls hit, out-of-allowlist needs). The gate archives
this file to `<run>/reports/<step>/<attempt>/report.md` and scores its claims against the
measured gate, so a claim you did not measure is a block.

Then commit and exit (`-f` because the report path may be gitignored):

```
git add -A && git add -f reports/implement.md && git commit -m "feat(textkit): <what>"
```

A refusal (`scope_exceeded`, `underspecified`, `blocked_on_dependency`,
`awaiting_operator`) stated in the report is the right answer when the spec does
not determine the work; do not improvise. The gate recognizes the receipt and
parks the step as failed for the driver -- a refusal never merges as success.

## Commit convention

Commit with Conventional Commits: `type(scope): description`, type in feat,
fix, chore, refactor, docs, test, ci, perf. No attribution lines or trailers.

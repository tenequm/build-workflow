# Brief: <phase> - <one line>

You are an executor in a git worktree of your own, on your own `agent/...`
branch. Read this whole file, then the spec sections cited below as the literal
token `SPEC <n>` (the build spec, sidecar `defaults.spec`) and the plan
sections cited as `PLAN <n>` / `PLAN <n.m>` (sidecar `defaults.doc`). Read
product-spec sections cited as `DESIGN <n>` only when the sidecar pins a
product spec. These are the only forms readiness resolves. Where this brief
names witness tests and contract files by path, those files are the
specification: do not reinterpret them from prose. Then read the machine plan
`.agents/build/plans/<slug>.yaml` (this step). Do the work, write the report,
then COMMIT on your branch: the commit is how the work reaches the gate and the
merge, and nothing runs after you exit. Do not ask questions; where something is
ambiguous, build the smallest faithful shape and record it under "Deviations".

## Context

<what exists, what is expected to be red, what earlier phases delivered>

## Items

1. <item, with a done-criterion the Validation block below can decide>
2. ...

## File allowlist

<paths>, plus your report file `<report path>`. The report path is not part of
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
<commands; do not clean the lint cache -- the gate provides a per-worktree one>
```

Report each command, its exit code and the last 30 lines of output.

## Rules

- The plan directory (spec.md, plan.md, facts.md, report.md) is driver-owned: never edit it.
- Edit the product spec only when the plan's Spec amendments section requires
  it and the file is in this step's allowlist.
- ASCII only in authored text. No em-dashes.
- Commit on your branch with a conventional message. Never push. Never main.
- Run the project formatter before writing the report.

## Report

Write `<report path>` in the worktree root: per item DONE / DEVIATED / SKIPPED
with file:line; Validation (per command); Deviations (with the alternative
rejected and why); Open (walls hit, out-of-allowlist needs). The gate archives
this file to `<run>/reports/<step>/<task>-<head>/report.md` and scores its claims against the
measured gate, so a claim you did not measure is a block.

Then commit and exit (`-f` because the report path may be gitignored):

```
git add -A && git add -f <report path> && git commit -m "<type>(<scope>): <what>"
```

A refusal (`scope_exceeded`, `underspecified`, `blocked_on_dependency`,
`awaiting_operator`) stated in the report is the right answer when the spec does
not determine the work; do not improvise. The gate recognizes the receipt and
parks the step as failed for the driver -- a refusal never merges as success.

## Commit convention

Commit with Conventional Commits: `type(scope): description`, type in feat,
fix, chore, refactor, docs, test, ci, perf. No attribution lines or trailers.

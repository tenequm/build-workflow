# Brief: <phase> - <one line>

You are an executor working in the git worktree `<worktree path>` (detached, no branch).
Read this whole file, then `docs/spec.md` sections <n, n.m>, then the plan
`.agents/build/plans/<slug>.yaml` (this step). Do the work, then write the
report. Do not ask questions; where something is ambiguous, build the smallest
faithful shape and record it under "Deviations".

## Context

<what exists, what is expected to be red, what earlier phases delivered>

## Items

1. <item, with a done-criterion the scorer can check>
2. ...

## File allowlist

<paths>. Stop and report instead of editing outside it.

## Validation (exactly, from <dir>)

```
<commands; clean lint cache first>
```

Report each command, its exit code and the last 30 lines of output.

## Rules

- `docs/spec.md` is driver-owned: never edit it.
- ASCII only in authored text. No em-dashes.
- Commit on your branch with a conventional message. Never push. Never main.
- Run the project formatter before writing the report.

## Report

Write `.agents/<report>.md` in the worktree root: per item DONE / DEVIATED /
SKIPPED with file:line; Validation (per command); Deviations (with the
alternative rejected and why); Open (walls hit, out-of-allowlist needs).
Then complete the task through the completion contract below. A refusal
(`scope_exceeded`, `underspecified`, `blocked_on_dependency`,
`awaiting_operator`) is the right answer when the spec does not determine the
work; do not improvise.

<completion contract block appended by the adapter>

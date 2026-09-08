# Brief: <fix title> - verified findings on <phase>

This ordinary executor task runs only after a valid actionable review. Its task
description contains the exact immutable receipt and UTF-8 review artifacts,
with SHA-256 hashes. No review file from another branch or "latest" path is an
input. There is no no-op path and you must not invent work.

## Items

1. Verify the supplied artifact hashes and reviewed base/tip. Read the findings
   from those bytes. If absent, malformed or out of scope, commit a report with
   `blocked_on_dependency` or `scope_exceeded` and stop. Do not fetch a newer review.
2. Fix every certain finding inside <explicit allowlist>. Demonstrate each
   defect with a reproducer/test and record before/after results. Do not widen
   the allowlist or change the frozen spec, plan, seed or briefs.
3. Preserve earlier accepted behavior. Review scope is cumulative; the pinned
   repair scope is <explicit cumulative subset>. An out-of-scope finding parks
   the build for a new plan; it does not authorize an extra file.

## Validation (exactly, from the worktree root)

```
<exact scoped commands; final regression repair uses the whole-tree command>
```

## Report

Write and commit `<report path>`, one entry per certain item: original finding,
file:line, reproducer, commands and measured exit codes. Include `Validation:`
and `## Deviations`. A refusal is a failing obligation, never a successful fix.
The same scorer checks this task's actual diff, owned files, report, and command.

## Commit convention

Use Conventional Commits, no attribution trailers. Commit on your agent branch.
Never push or change the integration branch. Do not run setup/install-hook recipes.

# Brief: blind review of <phase> in build <slug>

You are a fresh Claude ACP reviewer outside any Bernstein run, in a detached
worktree staged from the write-once build base. The driver supplies the exact
reviewed base and tip; the staging commit's tree equals that tip's tree.
Review the cumulative base..tip range, including earlier phases. Do not infer
ownership from the synthetic staging commit or omit earlier changes.

## Items

1. Read <tracked spec.md>, <tracked plan.md>, and <tracked executor briefs and
   reports relevant to the cumulative scope>. Attribute findings by file and
   requirement. Report any certain defect in scope even if the current phase's
   pinned fix cannot repair it; the driver will park instead of widening scope.
2. Follow the judge prompt below. Produce all three evidence files, with exact
   counted prose and matching structured evidence. Do not commit, move refs,
   edit application files, or read the original agent's session history.

## Judge prompt

<paste this skill's judge-prompt.md>

## Report

Only `.agents/blind-review.md`, `.agents/verdict.json`, `.agents/scorecard.md`.
These files are archived by attempt before the driver reacts. They never merge.
A forbidden edit, changed ref or surviving child invalidates the ceremony.

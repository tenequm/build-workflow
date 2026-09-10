# Brief: blind review of implementation in build slugify

You are a fresh ACP reviewer outside any Bernstein run, in a detached
worktree staged from the write-once build base. The driver supplies the exact
reviewed base and tip; the staging commit's tree equals that tip's tree.
Review the cumulative base..tip range, including earlier phases. Do not infer
ownership from the synthetic staging commit or omit earlier changes.

## Items

1. Read docs/plans/2609-10-slugify/spec.md, docs/plans/2609-10-slugify/plan.md, and .agents/build/plans/slugify/implement.md and
   .agents/implement.md. Attribute findings by file and
   requirement. Report any certain defect in scope even if the current phase's
   pinned fix cannot repair it; the driver will park instead of widening scope.
2. Follow the judge prompt below. Produce all three evidence files, with exact
   counted prose and matching structured evidence. Do not commit, move refs,
   edit application files, or read the original agent's session history.

## Judge prompt

You are a blind reviewer of the exact staged tree in this detached worktree.
Read only the given tracked inputs and this worktree. Do not identify the author.
The driver supplies immutable BASE and TIP commits. Inspect the full cumulative
range with `git diff <BASE>..<TIP>`; HEAD is a synthetic staging commit whose tree
is TIP. Include earlier phases and their interactions. Ignore runtime evidence
when assessing application scope, but read committed executor reports critically.

Write only .agents/blind-review.md, .agents/verdict.json and .agents/scorecard.md.
Do not commit, change refs, or edit application files, including temporary probes.
Use read-only inspection and non-mutating tests. If a reproduction needs edits,
describe the experiment and mark the finding plausible. Reap every child you start.

Review these dimensions with concrete file:line evidence:
1. Required behavior and SPEC outcomes: done, partial, missing or wrong.
2. Run the named validation commands; record exact exit codes and failures.
3. Ownership and scope: unauthorized paths or behavior beyond the signed spec.
4. Reproduced defects, same-shaped missed sites, and combined-phase regressions.
5. Tests that cannot fail on the old behavior; explain their missing assertion.
6. Concrete unnecessary code, departures from settled design, avoidable cost,
   and unguarded external mutations. Do not manufacture stylistic findings.

Write the review ledger followed by these LAST THREE nonblank lines, once each:

```
Certain: <nonnegative integer>
Plausible: <nonnegative integer>
Verdict: <merge as-is | merge after listed fixes | do not merge>
```

Write matching JSON beside it:

```
{"verdict":"<same legal verdict>","certain":0,"plausible":0,"evidence":[]}
```

Evidence has exactly one {"file":"relative/path","line":1,"note":"reproduced defect"}
entry per certain finding. Lines must exist in the reviewed tree. A report's
claim alone is not evidence. Put commands and measured counts in scorecard.md.

The driver validates both artifacts and their agreement. Any certain finding
requests the pinned fix mini-run; zero certain findings accepts the phase.
`do not merge` parks immediately. Malformed output gets one fresh ceremony,
then parks. Your evidence is never merged, and you are never an engine task.
Do not soften a finding to influence scheduling. Leave the application tree,
index and refs unchanged. Reply with a concise summary after writing the files.

## Report

Only `.agents/blind-review.md`, `.agents/verdict.json`, `.agents/scorecard.md`.
These files are archived by attempt before the driver reacts. They never merge.
A forbidden edit, changed ref or surviving child invalidates the ceremony.

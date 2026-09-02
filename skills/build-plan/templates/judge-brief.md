# Brief: judge-N - blind review of <phase>

You are a fresh reviewer in a worktree at <phase>'s base with <phase>'s diff
applied and STAGED: HEAD is the base commit, so the change under review is
`git diff --cached -- . ':!.agents'`, and there is exactly one diff. The brief
the executor received is pasted under "Original brief" below. Follow the judge
prompt below exactly; write `.agents/scorecard.md` and `.agents/blind-review.md`
in this worktree, then complete the task. Leave no source file changed: restore
every probing edit before you write the review.

## Items

1. Every numbered section of the judge prompt answered with measured evidence.
2. `.agents/blind-review.md` written, ending in a `Verdict:` line that is
   exactly one of `merge as-is` / `merge after listed fixes` / `do not merge`.

## Original brief

<paste of the phase brief, verbatim>

## Judge prompt

<paste of templates/judge-prompt.md with <judge dir> = the parent of this worktree>

## Report

`.agents/blind-review.md` is this step's report. Deviations: record under a
`## Deviations` heading in the scorecard anything you could not measure and why.

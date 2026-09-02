# Brief: judge-N - blind review of <phase>

You are a fresh reviewer in the worktree `<worktree>` at the merged state after
<phase>. Compute the diff under review as `git diff <base>...HEAD -- . ':!.agents'`.
The brief the executor received is at `.agents/briefs/judge-N.md` (this file's
"Original brief" section). Follow the judge prompt below exactly; write
`.agents/scorecard.md` and `.agents/blind-review.md` in this worktree, then
complete the task. Never edit source files.

## Original brief

<paste of the phase brief>

## Judge prompt

<paste of templates/judge-prompt.md with <judge dir> = this worktree>

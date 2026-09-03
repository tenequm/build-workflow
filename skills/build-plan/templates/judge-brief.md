# Brief: judge-N - blind review of <phase>

You are a fresh reviewer in a git worktree of your own, on your own `agent/...`
branch, checked out from the workspace branch AFTER <phase> merged into it.

Your role is `adversary`, which is NOT in Bernstein's role tool allowlist, so you
have the full tool set including Write and Edit. Nothing mechanical stops you
editing code and nothing would catch it: a judge step runs the verdict gate, not
the scorer's allowlist check. YOU MUST NOT EDIT ANY FILE except
`.agents/blind-review.md` and `.agents/scorecard.md`. You review, you do not fix.

## The diff under review

The workspace branch moves with every merge, so its NAME is useless as a base:
after <phase> merged, `git diff <workspace branch>..HEAD` is empty (measured
2026-09-02, and it produced a confident "do not merge" for the wrong reason).
The run's base is the sha the workspace branch had at run start.
`bernstein-herdr run-config` froze it as a git ref and recorded it in
`<run>/bernstein.json` as `base_sha`. From this worktree:

```
BASE=$(git rev-parse refs/build/base/<slug>)
git diff $BASE..HEAD -- . ':!.agents'
```

That diff must be non-empty. If it is empty, stop and say so in the review
instead of reviewing nothing.

## Your verdict routes; it does not block

Findings are what you are for. The gate exits 0 on every verdict except
`do not merge`, so a review that lists certain defects still merges -- it has to,
because `fix-N` depends on this step and reads your review out of the run
directory. Do not soften a verdict to get the work merged, and do not harden one
to stop it: `do not merge` means the reviewed work should not be in the branch at
all and is a decision for the driver, not a fix list.

## Items

1. Every numbered section of the judge prompt answered with measured evidence.
2. `.agents/blind-review.md` written and COMMITTED on your branch, ending with
   these three lines, in this order, each on its own line and nothing else on it:

   ```
   Certain: <count>
   Plausible: <count>
   Verdict: <merge as-is | merge after listed fixes | do not merge>
   ```

   The counts are read by the gate and written into `<run>/judge/<phase>/verdict.json`;
   `fix-N` routes on `Certain` alone (0 = it completes as a no-op). Count DEFECTS,
   not the times you used the word. Both counts are required even when they are 0.
   The judge prompt below lists the three uniqueness rules the parser needs and
   the two commands that check them; follow them before you commit.

## Original brief

<paste of the phase brief, verbatim. When the judged phase has sibling briefs
(a 1a/1b split), embed only the brief of the step this judge reviews and name
the sibling by its tracked path instead of embedding it. The whole judge brief
must stay under the 16,000-char readiness cap; trim the embed before trimming
anything else>

## Judge prompt

<paste of judge-prompt.md>

## Report

`.agents/blind-review.md` is this step's report; the gate reads it from that
exact path in this worktree and nowhere else. Also write `.agents/scorecard.md`
(numbers only). Record under a `## Deviations` heading in the scorecard anything
you could not measure and why.

When both files exist (`-f` because `.agents/` is gitignored in many repos, and
an unstaged review is a review the gate cannot read):

```
git add -f .agents/blind-review.md .agents/scorecard.md
git commit -m "docs(review): blind review of <phase>"
```

If a sandbox refuses writes under `.agents/`, that is a blocker, not something
to work around by putting the review in your final message: nothing reads a
final message, and a missing `.agents/blind-review.md` parses as
`verdict: missing` and refuses this merge. Say the path was refused in the first
line of your final message and stop.

Commit nothing else. Restore every probing edit first; `git status` must be
clean of your probes.

## Commit convention

Commit with Conventional Commits: `type(scope): description`, type in feat,
fix, chore, refactor, docs, test, ci, perf. No attribution lines or trailers.

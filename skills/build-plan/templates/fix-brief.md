# Brief: fix-N - judge findings on <phase>

The judge that reviewed <phase> merged whatever its verdict was; the verdict is
routing, not a block. So this step ALWAYS runs, and its first job is to decide
whether there is anything to do.

## Items

1. Read `<run dir>/judge/<phase>/verdict.json` and
   `<run dir>/judge/<phase>/blind-review.md`. The run directory is at the REPO
   ROOT, outside this worktree: read it with an absolute path
   (`.agents/build/runs/<slug>/judge/<phase>/`). `verdict.json` carries
   `verdict`, `certain` and `plausible`.
2. NO-OP PATH -- take it when `certain` is 0 (whatever the verdict says, `merge
   as-is` included). Write `.agents/fix-N.md` with the verdict line and the two
   counts quoted, one sentence saying no certain defect was reported and nothing
   was changed, and `## Deviations\n\nnone`. Then:

   ```
   git add .agents/fix-N.md
   git commit -m "docs: fix-N no-op, judge reported 0 certain defects"
   ```

   That commit is the whole step. `.agents/` is excluded from the gate's diff
   and from the allowlist check, so the gate sees zero changed files and passes.
   Do not touch a source file to "have something to show"; do not open the phase
   diff looking for work the judge did not report.
3. FIX PATH -- `certain` is 1 or more. Fix every defect the review labels
   certain, in the review's order, each with a test that fails before and passes
   after. Treat a plausible defect as an item only when the review gives a
   reproduction. Same allowlist as <phase>. Validation as in <phase>'s brief.

## Report

`.agents/fix-N.md`, on both paths. On the fix path, one entry per certain item
with file:line, the test that now covers it, and the review's own wording of the
defect. Record anything you did not fix, and why, under `## Deviations`.

# Brief: fix-N - judge findings on <phase>

The judge that reviewed <phase> merged whatever its verdict was; the verdict is
routing, not a block. So this step ALWAYS runs, and its first job is to decide
whether there is anything to do.

## Items

1. Read `verdict.json` and `blind-review.md` for <phase>. The run directory is
   at the REPO ROOT, outside this worktree, so use the absolute path:

   ```
   <absolute repo root>/.agents/build/runs/<slug>/judge/<phase T>/
   ```

   `<phase T>` is the judged step's title slug: lowercase, every non-alphanumeric
   run replaced by `-`, CUT TO 48 CHARS (a hand-written full title does not
   resolve). `verdict.json` carries `verdict`, `certain`, `plausible` and
   `counts_declared`, and it exists only there -- it is driver-side. The review
   itself the judge committed, so `.agents/blind-review.md` is also in THIS
   worktree; if the run directory is unreadable from here, take the same three
   facts from that file's last three lines (a legal verdict string, and both
   counts present as `Certain:` / `Plausible:` lines -- absent lines mean
   `counts_declared: false`).
2. NO-OP PATH -- take it ONLY when all three hold: `verdict` is one of the three
   legal strings (`merge as-is`, `merge after listed fixes`, `do not merge`),
   `counts_declared` is `true`, and `certain` is 0. Write `<report path>` with
   the verdict line and the two counts quoted, one sentence saying no certain
   defect was reported and nothing was changed, and `## Deviations\n\nnone`.
   Then:

   ```
   git add -f <report path>
   git commit -m "docs: fix-N no-op, judge reported 0 certain defects"
   ```

   `-f` because `.agents/` is gitignored in many repos, and an unstaged report
   means a commit of nothing, which the gate blocks. That commit is the whole
   step: `.agents/` is excluded from the gate's diff and from the allowlist
   check, so the gate sees zero changed files and passes. Do not touch a source
   file to "have something to show"; do not open the phase diff looking for work
   the judge did not report.
3. REFUSAL PATH -- `verdict` is `missing` or `unclear`, or `counts_declared` is
   `false`. The review either never landed or cannot be trusted to route this
   step, and a `certain: 0` on that path is a parser fallback, not a finding.
   Do not fix anything and do not take the no-op path. Write `<report path>`
   with `blocked_on_dependency`, the exact `verdict.json` contents, and one line
   saying the judge must be re-run; commit it as above so the report exists, and
   say the same in the first line of your final message. The driver decides what
   happens next.
4. FIX PATH -- a legal verdict, counts declared, `certain` 1 or more. Fix every
   defect the review labels certain, in the review's order, each with a test that
   fails before and passes after. Treat a plausible defect as an item only when
   the review gives a reproduction. Same allowlist as <phase>.

## Validation (exactly, from the worktree root)

```
<copy the exact commands from <phase>'s brief's Validation block>
```

Readiness rejects any brief whose `## Validation` is prose without a fenced
block, so the generator must fill the fence above, never replace it with a
sentence.

## Report

`<report path>`, on every path. On the fix path, one entry per certain item with
file:line, the test that now covers it, and the review's own wording of the
defect. Record anything you did not fix, and why, under `## Deviations`.

## Commit convention

Commit with Conventional Commits: `type(scope): description`, type in feat,
fix, chore, refactor, docs, test, ci, perf. No attribution lines or trailers.

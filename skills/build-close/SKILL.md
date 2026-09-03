---
name: build-close
description: "Stage 5 of the build workflow: converge the merged branch. Runs polish-new over the whole branch, a whole-branch blind judge, fix rounds until a review round warrants no edits, then writes the final summary, runs.jsonl rows and handoff.md. Use after a Bernstein run ends. Triggers: /build-close, close the build, finish the branch."
---

# build-close

Input: `<run>` = `.agents/build/runs/<slug>`, after `bernstein run` ended.
Output: `<run>/handoff.md`, final rows in `<run>/runs.jsonl`, a branch ready for
the user to merge. The driver never merges to main.

1. Read what the run left, before anything else:

       cat <run>/ledger.md
       python3 -c "import json,sys;[print(json.dumps(json.loads(l))[:200]) for l in open('<run>/runs.jsonl')]"
       ls <run>/reports/*/latest/report.md <run>/judge/*/blind-review.md

   `<run>/reports/<T>/<task>-<head>/` holds ONE GATE ATTEMPT's `report.md`,
   `diff.patch`, `numstat.txt`, `status.txt`, and `latest` symlinks to the newest
   attempt; several directories under one `<T>` mean the step was retried, and
   the attempt that merged is the one whose `runs.jsonl` row has `blocked=false`; `<run>/judge/<phase T>/` holds `blind-review.md`,
   `scorecard.md` and the judge worktree `W/`. A `blocked` line in `ledger.md`
   with `do_not_merge=True` is a phase that never merged: its defects are fix
   items, not close items.
2. `polish-new` over the branch against the integration base
   (`git diff <base>..HEAD`).
3. Whole-branch blind judge: a fresh Opus subagent given
   `.agents/skills/build-plan/templates/judge-prompt.md` with `<judge dir>` =
   `<run>/judge/branch`, staged the same way a judge step is staged:

       git worktree add --detach <run>/judge/branch/W <base>
       git -C <run>/judge/branch/W apply --index <(git diff <base>..HEAD -- . ':!.agents')

   Findings become fix briefs committed at `.agents/build/plans/<slug>/close-N.md`
   and dispatched as a fresh `resolver` step; re-run the touched
   tests after every fix.
4. Stop when a review round warrants no edits.
5. Archive and journal:

       git worktree remove --force <run>/judge/*/W        # the judge worktrees
       git -C . worktree prune
       git log --oneline <base>..HEAD                     # the phases that landed
       printf -- "- %s close: %s commits, %s judge rounds, verdict %s\n" \
         "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$(git rev-list --count <base>..HEAD)" \
         "$(ls <run>/judge | wc -l)" "<final verdict>" >> <run>/ledger.md

   `<run>/` is untracked by design (`.gitignore` carries
   `.agents/build/runs/`); nothing in it is committed. Copy anything the next
   session needs into `handoff.md`.
6. `<run>/handoff.md`, ASCII, these headings and nothing else:

       # handoff <slug> <date>
       ## Outcome        one line: branch, what landed, what did not
       ## Phases         per phase: executor kind, wall_s, files, gate, judge verdict
       ## Defects        caught before merge vs found after, with file:line
       ## Open           what the next session must decide, and the spec sections at risk
       ## Merge          the exact `git merge` the user runs, and the checks to run first

   `/build-design` reads this file first on the next run.

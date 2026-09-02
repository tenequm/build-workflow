---
name: build-close
description: "Stage 5 of the build workflow: converge the merged branch. Runs polish-new over the whole branch, a whole-branch blind judge, fix rounds until a review round warrants no edits, then writes the final summary, runs.jsonl rows and handoff.md. Use after a Bernstein run ends. Triggers: /build-close, close the build, finish the branch."
---

# build-close

Input: run dir after `bernstein run` ended. Output: `<run>/handoff.md`, final rows in `<run>/runs.jsonl`, a branch ready for the user to merge.

1. `polish-new` over the branch against the integration base.
2. Whole-branch blind judge with `templates/judge-prompt.md`; findings become fix briefs to Codex; re-run touched tests after every fix.
3. Stop when a review round warrants no edits.
4. Summary: phases, defects caught before merge vs after, wall per block, executor and judge rows. Write `handoff.md`. The user merges to main.

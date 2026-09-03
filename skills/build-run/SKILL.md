---
name: build-run
description: "Stage 4 of the build workflow: launch and supervise a native Bernstein run of a ready plan. Writes the run config and the frozen base sha, starts bernstein run, watches the ledger and the run log, relays executor refusals and blocked gates to the user as one-line decisions, dispatches fix briefs. Never edits code in the driver session. Triggers: /build-run, run the plan, start the build."
---

# build-run

Input: `<run>` = `.agents/build/runs/<slug>`, readiness ledger clean. Output:
`<run>/runs.jsonl`, `<run>/reports/<T>/<task>-<head>/{report.md,diff.patch,numstat.txt,status.txt}`
(one directory per gate attempt, `latest` a symlink to the newest),
`<run>/judge/<phase T>/{blind-review.md,scorecard.md}`, `<run>/ledger.md`.

Bernstein spawns its own adapters. There is no herdr pane, no watcher process and
no adapter of ours in the loop: an executor is `codex exec` or `claude -p`, it
commits on its `agent/...` branch and exits, and `bernstein-herdr gate` runs in
its worktree before the merge. All commands run from the repo root.

1. Preflight:

       bernstein doctor                 # findings are advisory; none of them blocks a run
       git symbolic-ref --short HEAD    # the integration branch, never main
       bernstein-herdr ready --plan .agents/build/plans/<slug>.yaml   # READY, pins written

   Readiness now also fails when `~/.codex/config.toml` lacks
   `model_reasoning_effort = "high"` (Codex takes no effort flag, so that file is
   the only lock) and when any `role:` in the plan has no `role_model_policy`
   entry in `bernstein.yaml`. `bernstein.yaml` from
   `.agents/skills/build-run/templates/bernstein.yaml` must be COMMITTED.
2. Run config:

       bernstein-herdr run-config

   Writes `.sdd/runtime/run_config.json` (`merge_strategy: direct` -- on the
   default `pr` the approval gate pushes to origin and never merges back),
   refuses while a task server for this repo is still answering, refuses when
   another `bernstein` process still owns this root (it prints the `kill` line;
   run it yourself), refuses when `bernstein.yaml`'s `quality_gates.base_ref` is
   not the branch checked out at the root, and prints this run's port as
   `run with: --port N`. It also FREEZES the base: the integration branch's sha
   at run start, written to `<run>/bernstein.json` as `base_sha` and to the git
   ref `refs/build/base/<slug>`. That ref is what the judge diffs against; the
   branch name is useless to a judge because every merge advances it. Fix what
   run-config names and rerun until it exits 0. Use that N below; never assume
   8052.
3. Point the git hooks somewhere empty, AFTER readiness is READY and never
   before (readiness fails on a hook that exists, not on the remedy):

       mkdir -p .agents/build/nohooks && git config core.hooksPath .agents/build/nohooks

   Linked worktrees share `.git/hooks`, so a repo hook runs inside every agent
   worktree AND against Bernstein's salvage commit; one failing there cost
   phase-2's 20 files (2026-09-03). `core.hooksPath` lives in untracked
   `.git/config`, so it never reaches an agent's diff, and unlike `LEFTHOOK=0` it
   survives the adapters' filtered spawn env and a mid-run `lefthook install`.
   Unset it when the run is over (step 11).
4. Launch. `--wait` blocks, so background it and keep the driver free
   (`--from-plan` is a different, seed-driven path; do not use it):

       BERNSTEIN_SERVER_URL=http://127.0.0.1:<N> \
       nohup bernstein run .agents/build/plans/<slug>.yaml --auto-approve --quiet \
         --fresh --wait 1500 --port <N> > <run>/bernstein-run.log 2>&1 &

   `BERNSTEIN_SERVER_URL` is NOT optional. `--port` moves the server only; the
   URL that Bernstein writes into every agent prompt (`bernstein task complete`,
   the auth section) and into the claude adapter's hook commands comes from that
   env var or defaults to 8052 (`spawner_core._resolve_task_server_url`). Without
   it every executor's completion call goes to 8052: a stale server there answers
   401, nothing there answers "connection refused", the agent prints either in
   its final message, Bernstein's log scanner reads it as an auth/api failure and
   FAILS THE TASK AFTER ITS MERGE LANDED (measured 2026-09-03: three retries and
   a DLQ entry on a step that had merged at the first attempt).

5. Watch these, in this order, every 30-60 s:

       tail -3 <run>/ledger.md                  # one line per gate
       tail -1 <run>/runs.jsonl                 # one row per gate
       tail -5 <run>/bernstein-run.log
       bernstein status                         # tasks, agents; NO --port option exists.
                                                # Run it from the repo root: it resolves
                                                # the server from .sdd/runtime/server.port,
                                                # which run-config wrote. `--json` for a
                                                # machine-readable dump, `--mode expert`
                                                # for everything.
       tail -20 .sdd/runtime/spawner.log        # the argv of every spawn

   THE `Total tasks / Failed` BLOCK IS NOT THE END OF THE RUN. The wrapper
   printed it and exited on the FIRST task failure while the orchestrator went on
   spawning a retry that later merged (measured 2026-09-03: the block at 00:30:06
   read `Done: 0, Failed: 1`, real work ran until 00:35:57). The run is over when
   the block has printed AND `pgrep -f bernstein` names no process for this root
   AND the board shows no runnable task (`bernstein status`). Until all three,
   keep watching. Ignore the `Elapsed: 0s`; it is wrong. Kill any orphan the run
   leaves behind, or the next `run-config` refuses.
6. A BLOCKED GATE IS TERMINAL, and this is the path you will actually walk.
   `bernstein-herdr gate` exiting 1 is not a retry and not a quarantine: the
   merge is refused, the agent's branch is moved to `salvage/<agent>` (a
   graveyard branch, its work intact), a row lands in
   `.sdd/runtime/refused_merges.jsonl`, and the run ends UNHEALTHY. It is
   terminal only because the template sets `gate_repair_enabled: false`; on
   Bernstein's default `true` you instead get one `[GATE-REPAIR] <title>` task
   on the same branch and worktree, and the block becomes terminal on the second
   failure. What the driver sees, in the order it appears:

       tail -1 <run>/runs.jsonl     # the gate's own row FIRST: blocked=true and why
       cat .sdd/runtime/refused_merges.jsonl
       rg -n "Refusing to merge" <run>/bernstein-run.log .sdd/runtime/spawner.log
       git branch --list 'salvage/*'
       git log --oneline <base>..salvage/<agent>   # what the step actually did

   A `salvage/<agent>` branch alone does NOT mean a block: Bernstein also
   salvages untracked leftovers after a SUCCESSFUL merge. The block signals are
   the gate's `blocked=true` row and `refused_merges.jsonl`; check those first.

   BUT A SALVAGE THAT IS A RENAME OF THE INTEGRATION BRANCH IS A BRANCH-LOSS
   EVENT, and it is silent. Measured 2026-09-02: a resumed session salvaged AT
   THE REPO ROOT, committed the whole `.sdd/` tree and renamed the integration
   branch away --

       git reflog show --all | rg 'renamed refs/heads/'
       # Branch: renamed refs/heads/build/1a-clean to refs/heads/salvage/resolver-080be7c7

   -- so for the rest of the run no integration branch existed and the next step
   branched from a polluted HEAD. Check for it the moment any salvage branch
   appears, and again before you trust a run's result:

       git branch --list '<integration branch>'   # empty = it was renamed away
       git log --oneline -5 salvage/<agent>       # inspect: is the tip the WIP salvage commit?

   Recovery, after inspecting: drop the salvage commit if it is a `.sdd/` dump,
   then rename the branch back --

       git branch -m salvage/<agent> <integration branch>
       git -C . checkout <integration branch>

   -- and restart the run; anything merged after the rename landed on the wrong
   branch. The engine-side patch in flight is meant to stop the rename happening
   at all; until it lands, this check is the driver's.

   A MERGED TASK IS NEVER RE-GATED. Bernstein resumes a task whose merge already
   landed (measured: `phase-1a` merged at 22:25:39 and was re-gated `blocked=true`
   at 22:33:56, blocking a step that was done). The gate short-circuits only for a
   task that PASSED, on the sha its pass memo records, and only when that sha is
   both strictly ahead of the frozen `base_sha` and on the integration branch
   (both from `<run>/bernstein.json`). A BLOCKED attempt's memo does not count:
   when it did, the next attempt -- at the branch tip having committed nothing --
   was waved through and the task went `done` (2026-09-03). It then prints
   `gate: already merged` and exits 0 with no new row and no new archive. Every
   clause is load-bearing: "ancestor of the branch" ALONE is true of the base
   itself, so a step killed before it committed anything was waved through
   unscored and a whole acceptance run produced no `runs.jsonl` (2026-09-03).
   A step that commits NOTHING is scored, and blocks.

   ONE ROW PER ATTEMPT, not per task. Bernstein retries a task IN PLACE under the
   same id, and three such retries wrote three rows under one id (2026-09-03).
   Read `runs.jsonl` as a per-attempt log: no row at all means the executor died
   before the gate ran -- a dead step, not a clean one -- so check the board and
   the spawner log before reading silence as success. Each attempt also archives
   to `<run>/reports/<step>/<task>-<head>/`, with `latest` a symlink to the
   newest, so a retry no longer overwrites the evidence of the attempt that
   passed.

   The gate archives the diff and writes its row on the blocking path too, so
   the evidence is complete before you look. `bernstein quarantine list` is
   EMPTY after a block -- do not wait for a retry that never comes. The most
   common cause is an ALLOWLIST VIOLATION: the row's `allowlist_violations`
   names files the step had to touch and the brief did not grant. THE DRIVER
   DECIDES: widen the allowlist in the plan `files:` and the brief, commit,
   `/build-ready`, re-run the step; or cherry-pick the good half out of
   `salvage/<agent>` into a fresh briefed step; or accept the block and change
   the plan. Nothing is automatic, and the driver still does not edit the code
   itself.
7. THE ROOT CHECKOUT CAN MOVE UNDER YOU. Bernstein pre-creates warm-pool slots
   with an empty `worktree_path` (core/tasks/task_lifecycle.py:288-297), and a
   spawn that claims one resolves it to `Path("")` = the repo ROOT
   (spawner_core.py:4471-4479): it writes a task CLAUDE.md over yours and
   switches the root to `agent/<role>-<id>`. No seed key disables the pool. The
   gate refuses to score at the repo root, so the step blocks instead of merging
   garbage, but the root is left on the agent branch. Check it whenever a step
   blocks, and put it back:

       git symbolic-ref --short HEAD        # must be the integration branch
       git status --short                   # a stray CLAUDE.md is the tell
       git checkout <integration branch> && git checkout -- CLAUDE.md

8. A JUDGE STEP NEVER BLOCKS ON FINDINGS. `bernstein-herdr gate` on a step with a
   sidecar `judges:` exits 1 only on the verdict `do not merge` (or a missing
   `.agents/blind-review.md`); `merge after listed fixes` and any number of
   certain defects exit 0, so the review merges and `fix-N` spawns. The gate row
   and `<run>/judge/<phase>/verdict.json` carry `verdict`, `certain` and
   `plausible`; `fix-N`'s brief routes on `certain` and completes as a no-op
   (one report commit under `.agents/`, no source change) when it is 0. A
   `do not merge` IS terminal and IS a decision for you: read the review, then
   change the plan.
9. Relay: `underspecified` / `awaiting_operator` refusals and blocked gates go to
   the user as one line with the ledger excerpt and the row; the answer becomes a
   brief edit, a rerun of `/build-ready`, and a re-dispatch.
10. Never edit `bernstein_herdr` while a run is live. The gate imports it fresh in
   every worktree, so a mid-run edit changes the gate under a running step.
11. The driver never edits code. Fixes go to a fresh executor with a brief, a
   file allowlist and a per-item report.
12. On run end: `git config --unset core.hooksPath`, then offer `/build-close <run>`.

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
3. Point the git hooks somewhere empty, any time before the launch -- readiness
   fails on a hook that EXISTS, not on this remedy, and PASSes with the empty
   path already configured, so setting it first is fine and re-running readiness
   after it is safe:

       mkdir -p .agents/build/nohooks && git config core.hooksPath .agents/build/nohooks

   Linked worktrees share `.git/hooks`, so a repo hook runs inside every agent
   worktree AND against Bernstein's salvage commit; one failing there cost
   phase-2's 20 files (2026-09-03). `core.hooksPath` lives in untracked
   `.git/config`, so it never reaches an agent's diff, and unlike `LEFTHOOK=0` it
   survives the adapters' filtered spawn env and a mid-run `lefthook install`.
   Unset it when the run is over (step 12).
4. Launch DETACHED, in a session of its own (`--from-plan` is a different,
   seed-driven path; do not use it):

       python3 - <<'PY' | tee -a <run>/ledger.md
       import os, pathlib, subprocess
       run  = pathlib.Path("<run>")
       log  = run / "bernstein-run.log"
       env  = dict(os.environ, BERNSTEIN_SERVER_URL="http://127.0.0.1:<N>")
       cmd  = ["bernstein", "run", ".agents/build/plans/<slug>.yaml",
               "--auto-approve", "--quiet", "--fresh", "--wait", "<budget s>", "--port", "<N>"]
       with log.open("ab") as f:
           p = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, env=env,
                                start_new_session=True)
       print(f"- launched bernstein run: wrapper_pid={p.pid} log={log}")
       PY

   `start_new_session=True` is the point of the wrapper: it puts the run in its
   OWN session and process group, so a cleanup that kills the driver's process
   group cannot reach the orchestrator, the task server or the live agents.
   `nohup ... &` does not do this -- it only ignores SIGHUP, leaving the run in
   the driver's group, and a run died exactly that way mid-phase (`Signal 15
   received, stopping orchestrator`, 2026-09-03; the restart then rebuilt the
   board wrong, see below). Record the printed `wrapper_pid` and log path in the
   ledger, because they are now the only handle you have: stopping the run
   deliberately is `kill -TERM -<wrapper_pid>` (the negative sign kills the
   group).

   `--wait` IS A BUDGET, NOT A CONSTANT. Set `<budget s>` from this plan: the
   sum of the `scope:` buckets along the DAG's critical path, doubled. Fixed
   example numbers have been wrong every time (a 25-minute wait over a run that
   took 1h52m). When the budget lapses the WRAPPER exits; the orchestrator does
   not, so keep watching by step 5's rules rather than reading the wrapper's
   exit as the end of the run.

   AN INTERRUPTED RUN IS NOT RESUMED ONTO AN ADVANCED TIP. Neither a plain
   resume nor `--fresh` is safe once merges from this run are in the branch: a
   resume rebuilt the board as four newly open tasks (`Done: 0`) on the
   already-merged tip, and `--fresh` on that same tip re-runs completed tasks as
   duplicates. Two safe moves, and it is the user's call which: restore the
   frozen base (`git rev-parse refs/build/base/<slug>`, after archiving what
   merged) and run fresh; or write a new plan holding only the remaining work,
   with its own slug, and run that. `<run>/ledger.md` and `runs.jsonl` are what
   say which steps actually merged.

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
       rg -n "liveness_judgment|SIGTERM|Timeout after" .sdd/runtime/spawner.log | tail -5
       rg -n "409|ownership conflict" .sdd/runtime/spawner.log | tail -5

   THE TWO `rg` LINES ARE THE EVENTS THAT COST THE MOST WALL AND ARE INVISIBLE
   EVERYWHERE ELSE until they surface as a blocked gate:

   - `grace_s=` in a `liveness_judgment` line must show the value
     `bernstein.yaml` configures, and `Timeout after <n>s` must match the step's
     `scope:` bucket (small 900 / medium 1800 / large 3600). A `grace_s=90` or a
     `Timeout after 1800s` on a `scope: large` step means the tuning never
     reached the kill paths -- an engine not installed from the patched clone --
     and healthy agents will be SIGTERMed mid-turn (2026-09-03: a judge killed
     13 min into a review it had already finished measuring).
   - `HTTP 409 File ownership conflict` is a LOCK WAIT, not a stall. Bernstein
     file-locks a step's declared files, so a step whose allowlist intersects a
     concurrently open step's backs off (300 s) and retries until the other
     releases; `fix-N` against `phase-N+1` is the usual pair. Expected. Do not
     kill the run over it; if the wait is long, say so and wait.

   THE `Total tasks / Failed` BLOCK IS NOT THE END OF THE RUN. The wrapper
   printed it and exited on the FIRST task failure while the orchestrator went on
   spawning a retry that later merged (measured 2026-09-03: the block at 00:30:06
   read `Done: 0, Failed: 1`, real work ran until 00:35:57). The run is over when
   the block has printed AND `pgrep -f bernstein` names no process for this root
   AND the board shows no runnable task (`bernstein status`). Until all three,
   keep watching. Ignore the `Elapsed: 0s`; it is wrong. Kill any orphan the run
   leaves behind, or the next `run-config` refuses.
6. A BLOCKED GATE REFUSES THIS MERGE; WHETHER THE TASK IS OVER IS A SEPARATE
   QUESTION, and this is the path you will actually walk. `bernstein-herdr gate`
   exiting 1 is not a quarantine: the merge is refused, the agent's branch is
   preserved (below), a row lands in `.sdd/runtime/refused_merges.jsonl`, and
   the run reports UNHEALTHY. `gate_repair_enabled: false` in the template stops
   ONE thing -- the `[GATE-REPAIR] <title>` task Bernstein would otherwise post
   on the same branch and worktree. It cannot cancel a retry that another
   lifecycle path already scheduled: the agent-death path runs
   `retry_or_fail_task` independently, and in the live run it declared
   `verdict=retry ... attempt=1/2` BEFORE the gate refused that attempt, so a
   fresh agent was already running while the block was being written
   (2026-09-03). TREAT THE TASK AS TERMINAL ONLY WHEN THE BOARD AND THE SPAWNER
   LOG BOTH SHOW NO RETRY LEFT:

       tail -1 <run>/runs.jsonl     # the gate's own row FIRST: blocked=true and why
       cat .sdd/runtime/refused_merges.jsonl
       rg -n "Refusing to merge" <run>/bernstein-run.log .sdd/runtime/spawner.log
       rg -n "retry_or_fail_task" .sdd/runtime/spawner.log | tail -3   # retry vs permanent_fail
       bernstein status            # is a task still runnable, is an agent still up

   `verdict=retry ... attempt=N/M` means work continues; `verdict=permanent_fail`
   / `max_retries_exceeded` is the end of that task. Declaring the run over on
   the first block, or starting recovery then, fights an orchestrator that is
   healing itself.

   THE REFUSED BRANCH IS IN THE GRAVEYARD, NOT IN `salvage/*`. On the refusal
   path Bernstein moves the agent branch to `refs/graveyard/<sid>-<ts>` and
   writes a portable bundle beside it, then deletes `agent/<sid>`:

       git for-each-ref --sort=-creatordate refs/graveyard/
       git log --oneline <base>..refs/graveyard/<sid>-<ts>    # what the step actually did
       ls -t .sdd/graveyard/*.bundle                          # survives a gc

   (Legacy: runs from before this engine left a `salvage/<agent>` branch
   instead; `git branch --list 'salvage/*'` is still worth one look on an old
   run directory. A `salvage/<agent>` branch alone never meant a block either --
   Bernstein also salvages untracked leftovers after a SUCCESSFUL merge.) The
   block signals are the gate's `blocked=true` row and `refused_merges.jsonl`;
   check those first.

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
   EMPTY after a block -- the block is not a quarantine, and the retry, when
   there is one, comes from the lifecycle path above and not from there. The
   most common cause is an ALLOWLIST VIOLATION: the row's `allowlist_violations`
   names files the step had to touch and the brief did not grant. Once the
   retries are spent, THE DRIVER DECIDES: widen the allowlist in the plan
   `files:` and the brief, commit, `/build-ready`, re-run the step; or
   cherry-pick the good half out of `refs/graveyard/<sid>-<ts>` into a fresh
   briefed step; or accept the block and change the plan. Nothing is automatic,
   and the driver still does not edit the code itself.
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
   and `<run>/judge/<phase>/verdict.json` carry `verdict`, `certain`,
   `plausible` and `counts_declared`. `fix-N`'s brief takes the no-op path (one
   report commit, no source change) only when the verdict is one of the three
   legal strings AND `counts_declared` is true AND `certain` is 0; on a
   `missing` or `unclear` verdict, or undeclared counts, it refuses with
   `blocked_on_dependency` and the judge is yours to re-run. The parser does not
   enforce that: a missing review parses as `verdict: missing, certain: 0` and a
   malformed one as `unclear` with word-count fallbacks, and neither blocks the
   merge, so the brief's routing is the only guard. Read fix-N's report on every
   run: a refusal is a committed report like any other, so its gate PASSES and
   nothing else raises it. A `do not merge` IS terminal and IS a decision for
   you: read the review, then change the plan.
9. Relay: `underspecified` / `awaiting_operator` refusals and blocked gates go to
   the user as one line with the ledger excerpt and the row; the answer becomes a
   brief edit, a rerun of `/build-ready`, and a re-dispatch.
10. Never edit `bernstein_herdr` while a run is live. The gate imports it fresh in
   every worktree, so a mid-run edit changes the gate under a running step.
11. The driver never edits code. Fixes go to a fresh executor with a brief, a
   file allowlist and a per-item report.
12. On run end: `git config --unset core.hooksPath`, then offer `/build-close <run>`.

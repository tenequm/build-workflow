---
name: build-run
description: "Stage 4 of the build workflow: launch and supervise a native Bernstein run of a ready plan. Writes the run config and the frozen base sha, starts bernstein run, watches the ledger and the run log, relays executor refusals and blocked gates to the user as one-line decisions, dispatches fix briefs. Never edits code in the driver session. Triggers: /build-run, run the plan, start the build."
---

# build-run

Input: `<run>` = `.agents/build/runs/<slug>`, readiness ledger clean. Output:
`<run>/runs.jsonl`, `<run>/reports/<T>/{report.md,diff.patch,numstat.txt,status.txt}`,
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
3. Launch. `--wait` blocks, so background it and keep the driver free
   (`--from-plan` is a different, seed-driven path; do not use it):

       nohup bernstein run .agents/build/plans/<slug>.yaml --auto-approve --quiet \
         --fresh --wait 1500 --port <N> > <run>/bernstein-run.log 2>&1 &

4. Watch these, in this order, every 30-60 s:

       tail -3 <run>/ledger.md                  # one line per gate
       tail -1 <run>/runs.jsonl                 # one row per gate
       tail -5 <run>/bernstein-run.log
       bernstein status --port <N>              # tasks, agents
       tail -20 .sdd/runtime/spawner.log        # the argv of every spawn

   The run is over when the log prints its `Total tasks / Failed` block and no
   `bernstein` process still names this root (`pgrep -fl bernstein`). Ignore the
   `Elapsed: 0s` in that block; it is wrong. Kill any orphan the run leaves
   behind, or the next `run-config` refuses.
5. A BLOCKED GATE IS TERMINAL. `bernstein-herdr gate` exiting 1 is not a retry
   and not a quarantine: the merge is refused, the agent's branch is moved to
   `salvage/<agent>`, a row lands in `.sdd/runtime/refused_merges.jsonl`, and the
   run ends unhealthy. What it looks like:

       rg -n "Refusing to merge" <run>/bernstein-run.log .sdd/runtime/spawner.log
       cat .sdd/runtime/refused_merges.jsonl
       git branch --list 'salvage/*'
       tail -1 <run>/runs.jsonl     # the gate's own row: blocked=true, why

   The gate archives the diff and writes its row on that path too, so the
   evidence is complete before you look. `bernstein quarantine list` is EMPTY
   after a block -- do not wait for a retry that never comes. THE DRIVER DECIDES
   what happens next: re-brief and re-run the step, take the salvage branch
   apart by hand, or accept the block and change the plan. Nothing is automatic.
6. Relay: `underspecified` / `awaiting_operator` refusals and blocked gates go to
   the user as one line with the ledger excerpt and the row; the answer becomes a
   brief edit, a rerun of `/build-ready`, and a re-dispatch.
7. Never edit `bernstein_herdr` while a run is live. The gate imports it fresh in
   every worktree, so a mid-run edit changes the gate under a running step.
8. The driver never edits code. Fixes go to a fresh executor with a brief, a
   file allowlist and a per-item report.
9. On run end, offer `/build-close <run>`.

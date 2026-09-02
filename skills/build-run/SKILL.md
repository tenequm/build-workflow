---
name: build-run
description: "Stage 4 of the build workflow: launch and supervise a Bernstein run of a ready plan through herdr. Opens the herdr layout, writes the run config, starts bernstein run, arms the watches, relays executor refusals and judge failures to the user as one-line decisions, dispatches fix briefs. Never edits code in the driver session. Triggers: /build-run, run the plan, start the build."
---

# build-run

Input: `<run>` = `.agents/build/runs/<slug>`, readiness ledger clean. Output:
`<run>/runs.jsonl`, `<run>/reports/<T>/{report.md,diff.patch,numstat.txt,status.txt}`,
`<run>/judge/<phase T>/{blind-review.md,scorecard.md,W/}`, and
`<run>/shadow/<T>/` for any step whose sidecar declares `shadow:`.

All commands run from the repo root.

1. Preflight:

       bernstein doctor                 # findings are advisory; none of them blocks a run
       bernstein adapters list | grep herdr   # herdr-claude, herdr-codex, herdr-agy, herdr-fake
       git symbolic-ref --short HEAD    # the integration branch, never main
       bernstein-herdr ready --plan .agents/build/plans/<slug>.yaml   # READY, pins written

   The `missing` status column on the herdr adapters is expected (it looks for a
   binary of that name; the adapters launch through herdr). `bernstein.yaml`
   from `.agents/skills/build-run/templates/bernstein.yaml` names the gates and
   must be COMMITTED.
2. Run config:

       bernstein-herdr run-config

   Writes `.sdd/runtime/run_config.json` (`merge_strategy: direct` -- on the
   default `pr` the approval gate pushes to origin and never merges back),
   refuses while a task server for this repo is still answering, refuses when
   another `bernstein` process still owns this root (it prints the `kill` line;
   run it yourself), refuses when `bernstein.yaml`'s `quality_gates.base_ref` is
   not the branch checked out at the root, and prints this run's port as
   `run with: --port N`. Fix what it names and rerun until it exits 0. Use that
   N below; never assume 8052.
3. Layout (optional -- the adapter creates the workspace itself if
   `<run>/herdr.json` is absent):

       herdr workspace create --cwd "$PWD" --label build-<slug> --no-focus > /tmp/ws.json
       python3 -c "import json,pathlib;r=json.load(open('/tmp/ws.json'))['result'];pathlib.Path('<run>/herdr.json').write_text(json.dumps({'workspace':r['workspace']['workspace_id'],'root_pane':r['root_pane']['pane_id']}))"

   `bernstein live` in the root pane is the dashboard; it is a TUI, so start it
   in that pane, never in the driver's own. The adapter opens one tab per
   executor, judge and shadow lane in that workspace and never touches the
   driver's pane.
4. Launch. `--wait` blocks, so background it and keep the driver free
   (`--from-plan` is a different, seed-driven path; do not use it):

       nohup bernstein run .agents/build/plans/<slug>.yaml --auto-approve --fresh \
         --wait 1500 --port <N> > <run>/bernstein-run.log 2>&1 &

5. Watch these three, in this order, every 30-60 s:

       tail -3 <run>/ledger.md      # spawn / settled / completed / blocked / refused, per step
       tail -1 <run>/runs.jsonl     # one row per settle and per gate
       tail -5 <run>/bernstein-run.log

   The run is over when the log prints its `Total tasks / Failed` block and no
   `bernstein` process still names this root (`pgrep -fl bernstein`). Ignore the
   `Elapsed: 0s` in that block; it is wrong. Kill any orphan the run leaves
   behind, or the next `run-config` refuses.
6. Relay: `underspecified` / `awaiting_operator` refusals and judge failures
   after retries go to the user as one line with the ledger excerpt; the answer
   becomes a brief edit, a rerun of `/build-ready`, and a re-dispatch.
   Everything else is machine-handled. A blocked gate fails the task; Bernstein
   retries it and may then quarantine the title. Check before assuming:
   `bernstein quarantine list`, then `bernstein quarantine clear --task "<title>"`
   only if it is listed (never `rm -rf .sdd`, which also drops the run's own
   state).
7. Never edit `bernstein_herdr` while a run is live. Each watcher imported the
   package at spawn and loads its gate module lazily, so a mid-run edit crashes
   the gate on a half-old import.
8. The driver never edits code. Fixes go to a fresh executor with a brief, a
   file allowlist and a per-item report.
9. On run end, offer `/build-close <run>`.

---
name: build-run
description: "Stage 4 of the build workflow: launch and supervise a Bernstein run of a ready plan through herdr. Opens the herdr layout, writes the run config, starts bernstein run, arms the watches, relays executor refusals and judge failures to the user as one-line decisions, dispatches fix briefs. Never edits code in the driver session. Triggers: /build-run, run the plan, start the build."
---

# build-run

Input: run dir whose readiness ledger is clean. Output: rows in `<run>/runs.jsonl`, reports under `<run>/reports/`, judge ledgers under `<run>/judge/`, shadow captures under `<run>/shadow/`.

1. Preflight: `bernstein doctor`; `bernstein adapters list` shows herdr-claude, herdr-codex, herdr-agy; `bernstein.yaml` from `templates/bernstein.yaml` names the gates and is committed; `<run>/readiness/pins.json` exists and `bernstein-herdr ready` is clean; the repo root is checked out on the integration branch, never main.
2. `bernstein-herdr run-config` from the repo root: writes `.sdd/runtime/run_config.json` (`merge_strategy: direct` -- on the default `pr` the approval gate pushes to origin and never merges back), refuses while a task server for this repo is still answering, refuses when `bernstein.yaml`'s `quality_gates.base_ref` is not the branch checked out at the root, and picks this run's server port (printed as `--port N`, written to `.sdd/runtime/server.port` and `<run>/bernstein.json`; the watcher resolves the same file). Fix what it names and rerun until it exits 0.
3. Layout: `herdr workspace create --cwd <repo root> --label build-<slug> --no-focus`; write its ids to `<run>/herdr.json` (`{"workspace": ..., "root_pane": ...}`); run `bernstein live` in the root pane. The adapter opens one tab per executor, judge and shadow lane in that workspace and never touches the driver's own pane.
4. Launch `bernstein run <plan> --auto-approve --fresh --wait <s> --port <the port run-config printed>` (`--from-plan` is a different, seed-driven path); arm a watch on `.sdd/` task state and on refusals.
5. Relay: `underspecified` / `awaiting_operator` refusals and judge failures after retries go to the user as one line with the ledger excerpt; the answer becomes a brief edit and a re-dispatch. Everything else is machine-handled. A blocked gate fails the task, so Bernstein retries it and then quarantines the title: `bernstein quarantine list`, and `bernstein quarantine clear --task "<title>"` before re-dispatching (never `rm -rf .sdd`, which also drops the run's own state).
6. Never edit `bernstein_herdr` while a run is live. Each watcher imported the package at spawn and loads its gate module lazily, so a mid-run edit crashes the gate on a half-old import.
7. The driver never edits code. Fixes go to a fresh executor with a brief, a file allowlist and a per-item report.
8. On run end, offer `/build-close <run dir>`.

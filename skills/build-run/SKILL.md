---
name: build-run
description: "Stage 4 of the build workflow: launch and supervise a Bernstein run of a ready plan through herdr. Opens the herdr layout, starts bernstein run --from-plan, arms the watches, relays executor refusals and judge failures to the user as one-line decisions, dispatches fix briefs. Never edits code in the driver session. Triggers: /build-run, run the plan, start the build."
---

# build-run

Input: run dir whose readiness ledger is clean. Output: rows in `<run>/runs.jsonl`, reports under `<run>/reports/`, judge ledgers under `<run>/judge/`, shadow captures under `<run>/shadow/`.

1. Preflight: `bernstein doctor`; adapters `herdr-claude`, `herdr-codex`, `herdr-agy` resolve; agy worktree paths pre-trusted; the repo root is on the integration branch, never main.
2. Layout: one herdr workspace for the run: driver pane, `bernstein live` pane; executor and judge panes are opened by the adapter.
3. Launch `bernstein run --from-plan <plan>`; arm a watch on `.sdd/` task state and on refusals.
4. Relay: `underspecified` / `awaiting_operator` refusals and judge failures after retries go to the user as one line with the ledger excerpt; the answer becomes a brief edit and a re-dispatch. Everything else is machine-handled.
5. The driver never edits code. Fixes go to a fresh executor with a brief, a file allowlist and a per-item report.
6. On run end, offer `/build-close <run dir>`.

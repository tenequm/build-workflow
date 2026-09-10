# Operator acceptance

Run `just --justfile bernstein_operator/Justfile check` and
`just --justfile bernstein_operator/Justfile test -q` from the repository.
CI is intentionally deferred. The acceptance runner copies the locked native
source to a temporary directory, applies the exact prerequisites, and loads the
installed scorer entry point against that copy. It does not patch an existing
engine installation or make paid model calls.

| Contract | Executed evidence |
|---|---|
| Plugin reachability | `test_installed_gate.py` runs the installed registry, real seed parser and both native gate call sites, including merge-time surrogate IDs. Missing registration fails admission. |
| Real phase boundaries | `test_native_phases.py` runs real native servers, scheduler CLI, gates, merge, journal, WAL and quiescence in one workspace across two fresh run IDs. Only the executor adapter is replaced by a recording process. No future-phase task exists on the first server. |
| Teardown and recovery | The native phase test injects driver failure after teardown but before closure journaling, then resumes without another launch. Process tests check identity-bound launch recovery; ceremony tests reject and reap surviving children. Server death, no-start and low disk fail closed. No watchdog or bootstrap is started. |
| Conditional fixes | `test_phase_loop.py` tests the production workflow loop with recorded native/judge boundaries: pending fix, crash recovery, malformed-once, do-not-merge, cumulative scope and whole-build limits. `test_driver_recovery.py` covers lost POST responses and claimed/done/closed retries without duplicate creation. |
| Semantic cache | `test_cache_disabled.py` constructs the real orchestrator and executes its native claim/dispatch path against a populated real response cache. It covers startup, population after startup, reconstruction and retry metadata; dispatch reaches a scoring recording executor instead of completing from cache. This is not a full live-model retry benchmark. |
| Scorer authority | Observed owned/unowned and deletion diffs, dirty trees, missing commits, frozen documents, changed reports, all four refusal classes, content-bound memo reuse, landed deduplication, exact report/diff receipts and local-only merge-back. |
| Launch admission | Real direct task POST retains completion signals and concrete dependency IDs. Actual loader and janitor evaluate `path :: needle`. Linked-workspace readiness replays commands in a detached base. Backlogs, importable files, quarantine, missing gates and invalid configuration block admission. |
| Claude ACP ceremony | Real `acpx` talks through the budget/model/turn bridge to a recording ACP server. Separate ceremony tests stage real Git trees, bind the review range, reject application/ref mutation, reap processes and recover immutable receipts. No Claude provider invocation is used by the suite. |
| Evidence preservation | Native archives survive more than twenty later journals. Delivery uses native merge events or exact scored second-parent ancestry. Paired WAL claims are sealed only after proof. Close tests verify archive hashes, portable Git objects and refusal on code drift. |
| Independent skills | Vendored helper and template comparisons run locally. Each skill has its own scripts and templates; runtime code never reads a sibling skill. Hook capture/restoration is checked and refuses unrelated configuration changes. |

The source checkout used for real builds needs four prerequisite patches:
plugin-aware seed parsing, an effective semantic-cache disable switch,
local-only `safe_push`, and a quiescence self-stop that counts the `closed`
status a merged task is archived to. Readiness refuses an unprepared
installation. The development lock alone does not provide those patches to a
paid build.

The first real build (2026-09-10, a `textkit.slugify` fixture) exercised what no
recording can: a Claude Sonnet executor, a Codex executor, an Antigravity/agy
judge over generic ACP and a Claude judge over the pinned adapter, two phase
boundaries and real merges. It is what found the fourth patch above - every
recorded task reaches the quiescent tick as `done`, while a really merged one is
already `closed` - and the `--no-sources` install requirement. Judge transports
are `claude` (the bridge binds budget, model and turns; cumulative USD cost is
required evidence) and `acp` (any other ACP agent, model passed to acpx;
subscription agents report no cost, so the ceremony is recorded unmetered).

The driver parks uncertain effects; it does not promise automatic recovery from
every interrupted filesystem write. Tests inject interruption at durable-effect
boundaries and verify either reconciliation or a preserved unresolved obligation.
Model quality, provider authentication, real provider billing and application
specific validation commands remain properties of the eventual build environment.
The repository retains `bernstein_herdr/` after cutover.

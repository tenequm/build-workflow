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
| Teardown and recovery | The native phase test injects driver failure after teardown but before closure journaling, then resumes without another launch. Process tests check identity-bound launch recovery; ceremony tests reap a surviving child, name it in the receipt, and refuse one that outlives the reaping. Server death, no-start and low disk fail closed. No watchdog or bootstrap is started. |
| Conditional fixes | `test_phase_loop.py` tests the production workflow loop with recorded native/judge boundaries: pending fix, crash recovery, malformed-once, do-not-merge, cumulative scope and whole-build limits. `test_driver_recovery.py` covers lost POST responses and claimed/done/closed retries without duplicate creation. |
| Semantic cache | `test_cache_disabled.py` constructs the real orchestrator and executes its native claim/dispatch path against a populated real response cache. It covers startup, population after startup, reconstruction and retry metadata; dispatch reaches a scoring recording executor instead of completing from cache. This is not a full live-model retry benchmark. |
| Scorer authority | Observed owned/unowned and deletion diffs, dirty trees, missing commits, frozen documents, changed reports, all four refusal classes, content-bound memo reuse, landed deduplication, exact report/diff receipts and local-only merge-back. |
| Launch admission | Real direct task POST retains completion signals and concrete dependency IDs. Actual loader and janitor evaluate `path :: needle`. Linked-workspace readiness replays commands in a detached base. Backlogs, importable files, quarantine, missing gates and invalid configuration block admission. |
| ACP judge ceremony | Real `acpx` talks through the budget/model/turn bridge to a recording ACP server, and the bridgeless transport is checked for the turn, tool and empty-MCP bounds it asks acpx for instead. Separate ceremony tests stage real Git trees, bind the review range, reject application/ref mutation, reap processes and recover immutable receipts. No Claude provider invocation is used by the suite. |
| Evidence preservation | Native archives survive more than twenty later journals. Delivery uses native merge events or exact scored second-parent ancestry. Paired WAL claims are sealed only after proof. Close tests verify archive hashes, portable Git objects and refusal on code drift. |
| Independent skills | Vendored helper and template comparisons run locally, and `scripts/skill_isolation.py` greps every skill for a reference to a sibling's directory. Each skill has its own scripts and templates; runtime code never reads a sibling skill. Hook capture/restoration is checked and refuses unrelated configuration changes. |
| /review-pr deterministic spine | `test_review_contract.py` pins the findings schema (an unexecutable rubric is refused, a rubricless finding is capped at a suggestion, a credential is named and never reproduced), the diff index, and the verdict table's every row. `test_review_stage0.py` runs the house rules against real checkouts, including a pull request that edits the validation command and a test that passes with its change reverted. |
| /review-pr anchors | A finding outside a hunk, one on a file absent from the diff and one on a deleted file are all caught before a payload exists, because GitHub rejects a whole review atomically on one bad anchor. |
| /review-pr execution | `test_review_execution.py` executes rather than mocks: each rubric kind, a hunk-scoped revert, the gold gate's three outcomes, the cold-cache gate, and a suggestion applied and gated for real. It also asserts the sandbox blocks network and that the credential allowlist keeps a token out of an untrusted command. |
| /review-pr sessions | `test_review_sessions.py` drives real `acpx` against a recording ACP agent: a witnessed report succeeds, a clean exit with no report is retried once and then recorded as failed, a report that does not witness itself fails, a session that writes outside its allowlist parks the stage, an over-budget session parks, and a batch overlaps rather than queues. No provider is called. |
| /review-pr end to end | `test_review_fixture.py` materialises the seeded fixture and runs stages 0 to 4, asserting every planted defect, the injection reported without being obeyed, the re-executed claim mismatch, the dual-family agreement counts, the proven and the downgraded suggestion, and one append-only ledger row per finding. |

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

Two builds carried the whole lifecycle on 2026-09-10: a single phase whose
completion signals name both its code and its report reached `build_completed`
with a zero-certain judge verdict, and `/build-close` then regenerated the
report, merged to the primary, ran the whole-tree check on the merged tree,
preserved 48 evidence files, restored the captured hooksPath and removed the
workspace. One ran its executor on Claude Sonnet 5, the other on Codex
`gpt-5.6-terra`. An earlier attempt on `gpt-5.6-luna` failed repeatedly - the
agent wandered off its brief, wrote its report outside the declared path and
exited without committing - so executor model capability, not sandboxing, is
what that lane needs.

`/review-pr` is covered by the recording-agent layer only. Its model stages run as
driver-owned ACP sessions rather than engine runs, so no phase boundary, scorer or
merge contract applies to it; what a recording agent cannot reach is whether a real
model writes a rubric worth executing, which is what the precision ledger measures
over real pull requests. The two acceptance items that need paid runs - the #5737
ground-truth replay and a real weekly batch - are recorded as not yet run in
[the plan](plans/2609-11-review-pr.md).

The driver parks uncertain effects; it does not promise automatic recovery from
every interrupted filesystem write. Tests inject interruption at durable-effect
boundaries and verify either reconciliation or a preserved unresolved obligation.
Model quality, provider authentication, real provider billing and application
specific validation commands remain properties of the eventual build environment.
The repository retains `bernstein_herdr/` after cutover.

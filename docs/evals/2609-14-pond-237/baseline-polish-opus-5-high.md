# Baseline A: `/polish` on `claude-opus-5` (high)

Reviewer A of three. See [the comparison index](README.md).

| | |
|---|---|
| Skill | `/polish` v3.1.0, fix mode |
| Driver | `claude-opus-5`, high effort, Claude Code |
| Lenses | 4 subagents on the same model (cleanliness, design/reuse, efficiency, side-effect gating) |
| Tree | worktree `polish/237` at head `1c32a58`, full repository, not a diff |
| Gates before review | `cargo fmt --check` and `cargo clippy --all-targets -D warnings` both pass |
| Ran | 2026-09-14, 12:49-13:02Z (about 12 minutes) |
| Result | **28 findings** across 4 categories, plus 4 dropped after validation |

Every finding below was re-read against the code by the driver before it was
kept. Line numbers refer to the head tree.

---

## Review Findings - [PR #237: fix(sync): fail the adapter, not the run, when a source dir is absent](https://github.com/tenequm/pond/pull/237)

This is fix mode. The review ran in the new worktree slot 2 (`polish/237`, at `1c32a58`). Phase 1 is clean: `cargo fmt --check` and `cargo clippy --all-targets -D warnings` both pass. Every finding below was re-read against the code, and the line numbers refer to slot 2.

### Correctness (5 issues)

1. **`main.rs:4133-4138` - the all-absent branch writes to stderr before it records the adapter.**
   - It calls `emit_source_missing(...)?`, then pushes the entry.
   - If that stderr write fails (any error other than EPIPE), the `?` returns before the last-sync record is written (`:4141`) and before the ok JSON document (`:4165`). In `--format json`, stdout ends up empty, which breaks the one-document contract.
   - The import stage already does this the right way round (`:5245`, "Record before emitting").
2. **`main.rs:5237`, `:6892` - a mistyped adapter name with an absent path now looks like a missing source.**
   - Resolving the whole config (`resolve_adapters(None)`, `config.rs:696-716`) never checks adapter names. So `[adapters.cdoex-cli] path="/nope"` produces a `source_missing` entry and exit 0, where main exits 1 with `unknown adapter`.
   - `pond status` shows it as `source_missing`, and the dry run still hard-errors (`:4829`). That is three different answers for one typo.
   - Pre-existing part: a typo whose path *exists* only fails inside `sync_with_progress` (`:5899`), after earlier adapters have already committed.
3. **`main.rs:4461-4473` - the new `openclaw_read_failed` gate silently turns off deletion detection for every openclaw root.**
   - It trips when any openclaw pass is failed or degraded, and degraded includes one corrupt file or one session the validator rejected.
   - A file that stays corrupt therefore hides the erase-pending report permanently. `reconciliation` stays `None`, which looks exactly like "openclaw not in scope".
   - The failed-source half of the gate is redundant: `list_agents` already maps `NotFound` to `Ok(vec![])` (`openclaw.rs:425`).
   - What actually needs handling is an unreadable `agents/` root, where `list_agents` errors and `?` fails the run (`:4477`). That can be caught per root inside `reconcile_deletions`: warn and preserve, like `deleted_archive_ids` now does.
4. **`missing_source.rs:567-581` - `non_utf8_path_is_a_named_error_not_a_panic` builds its env by hand.**
   - It leaves out `XDG_DATA_HOME`, `XDG_CACHE_HOME` and `env_remove("RUST_LOG")`.
   - Its resolve error only fires after the lock and `open_store` (create=true). On a machine with `XDG_DATA_HOME` set, the test opens or creates a store in the developer's real data dir.
5. **`main.rs:4038-4044`, `:4119` - a resolve error (e.g. `pond sync <typo>`) still waits on the lock, creates the store, loads the embedder, and overwrites the last real sync's record before failing** (pre-existing).
   - The PR has the resolve result in hand at both checks and discards it on purpose (commit `162e4d6`, which keeps the counted error document).

**Side-effects checked:** flock, store creation, embedder load, Lance commits, freshness-cache writes, the last-sync record, the stdout document, reconciliation, and config and schedule writes.
- Explicit-narrowing bails come before the lock, store and first pass, in both real sync and dry run.
- The all-absent short-circuit sits after the lock and before `open_store`, and `--no-wait` still returns ahead of it.
- Counts are written to `report` before `import_result?`.
- Reconciliation is detection-only: it uses read-only SQLite and deletes nothing.
- No config or schedule writes happen on the sync or status paths.

### Design (7 issues)

1. **`main.rs:4113-4175` - the all-absent short-circuit hand-copies the ok document, the last-sync record and the "done" line** that the shared tail already produces from `SyncReport::default()`.
   - That is a third copy next to `attach_adapter_verdicts`, which exists to stop exactly this drift.
   - Suggested shape: `let outcome = if all_absent { fill failed_adapters; Ok(()) } else { run_sync_stages(..) }`, then let the shared tail finish. This also fixes Correctness #1 and removes about 45 lines.
2. **`main.rs:1326`, `:7069`, `:1303-1308`, `:7000` - the text for a never-synced store drifted in three ways.**
   - Switching to `render_local_status` added `last sync  never on this host - run pond sync`. It prints right after "run `pond init`" (a dead end), after a config error, or as a duplicate of the same advice.
   - `has_adapters` resolves the config again, even though `local_status` just did.
   - A missing-source row renders as `cannot read this source - source missing: <path>`.
3. **`main.rs:5366` vs `:5345` - `failed_adapters[].path` is shown from the expanded path, while `degraded_adapters`, status and dry-run show the raw one.** With `path = "$VAR/x"` these differ, so tooling that joins on `(name, path)` breaks. Taking the display string from `source_path` everywhere fixes it.
4. **`main.rs:5392-5421` - `bail_when_explicit_entry_source_missing` has a pointless bool and a small race.**
   - The bool is always `true`, or was already checked by the caller.
   - It checks the disk again instead of using the `missing` value the caller has in hand. If the root reappears between the two checks, a narrowed run records a `FailedAdapter` and exits 0.
   - Fix: drop the bool and pass `missing` through.
5. **`main.rs:6516-6538` vs `:6612-6631` - `status_json_empty` copies the `local` and `schedule` blocks from `status_json` key for key.** `local_adapters_json` was extracted, but one level too low; extract `local_status_json` and `schedule_json` instead.
6. **`main.rs:4579-4633` - four JSON attach helpers repeat the same `if let Value::Object(map)` insert.**
7. **`main.rs:4785` and `:6832` - `RowError` and `LocalAdapterStatus{error, reason}` model the same invariant.** Status keeps it as two parallel `Option`s.

### Efficiency (3 issues)

1. **`main.rs:4769-4777` - an all-absent `pond sync --dry-run` still creates the store and builds the rowmap before it checks rows.** On a new host that build is a full scan of `messages`, which is costly on remote storage. This is issue #236's own repro command, and real sync already skips it. Fix: run the all-absent check before `open_store`.
2. **`main.rs:5198` - on a host where every source is absent, each `serve --with-sync` tick builds the rowmap before the pre-flight check.** Hoisting the all-absent check above the oracle setup fixes it, and the `:5217` first-sync-notice guard can then go.
3. **`missing_source.rs:1262-1283` - `an_all_absent_host_does_not_repeat_the_first_sync_notice` spawns two syncs to pin a notice that its own doc says is unreachable by construction.** `all_absent_whole_sync_skips_the_store_but_takes_the_lock` already covers it.

### Cleanliness (13 issues)

1. `main.rs:1296-1300`: a comment says "the host this PR is about", which will rot once merged.
2. `main.rs:4855-4857`, `:5205-5207`, `:6503`, `missing_source.rs:1260`: comments describing what the code "used to" do or "now" does.
3. `missing_source.rs:980`: `row["plan"].is_null()` can never fail, because status rows have no `plan` key.
4. `missing_source.rs:491`, `:516`, `:1196`: three TOML config strings with 13 literal spaces inside them, from a broken `\n\` line join.
5. `missing_source.rs:1180-1184`: the test name says "unenumerable", but the fixture is a regular file. `is_dir()` returns `Ok(empty)`, so the new Err arm is never reached.
6. `handlers.rs:363-368`: "we don't currently distinguish them" is contradicted by the `kind != "session"` guard two lines below.
7. `sessions.rs:3790-3792`: the doc calls `unreadable_events` separate from drops, but it is also added to `dropped_events` (`handlers.rs:423`). Also, the `skipped_files` doc at `:3784` is stale (pre-existing).
8. The old "visible skips" wording survives the switch to `Unimportable`:
   - `nanoclaw.rs:165`, `:707`, `:714`
   - `tests/.../nanoclaw.rs:6`
   - the test name `codex_provider_sessions_are_visibly_skipped` (`:228`)
9. `main.rs:6066-6069`, `:6090-6092`: the "don't tick `pos`" comments don't mention `Unimportable`.
10. `missing_source.rs:135`, `:156`, `:1154`: the Windows state-dir branch is repeated three times, and that is the quirk whose mistake makes absence assertions pass vacuously.
11. `missing_source.rs:834`, `:91`, `:278`: the test name `dropped_events_are_attributed_to_their_adapter` uses the wrong population. "repro B" and "decision 2" point at documents the file never names.
12. `unreadable_source.rs:117` (out of diff): "`status` reports `local: null` until a store exists" is now false, and the extra sync it justifies is no longer needed.
13. PR body: it cites "spec 7.2" for additive evolution. 7.2 is the request envelope; the right section is 7.8.

### Dropped after validation

1. A stderr EPIPE mid-import makes the process exit 0 before the last-sync record and the document (`lib.rs:123`). This is a project-wide policy that predates the PR; the only new piece is ordering, which Correctness #1 covers.
2. `pond status` on a never-synced store now walks every source (`discover`). This is intended, and it costs the same as the initialized branch already pays.
3. Per-event allocations in `handlers.rs` all sit behind `is_none()`, so at most one per adapter. The repeated resolves and `try_exists` calls are config parsing on a cold path.
4. The integration suite has no sleeps. The lock test uses the same flock primitive, and the seeding syncs are needed.

**Total: 28 issues across 4 categories**

**Recommendation:**

- **Fix:**
  - Correctness #1-4
  - Design #1-5 (D1 also fixes C1)
  - Efficiency #1-3
  - Cleanliness #1-12
  - Cleanliness #13 as a PR body edit through REST
- **Defer Correctness #5 to a follow-up issue.** The fix reverses a deliberate choice this PR pinned with a test (`162e4d6`), and the spec allows either error-document shape, so it needs your call.
- **Skip Design #6-7.** They are marginal churn, and the one user-visible symptom of D7 is already fixed in D2.

**Awaiting approval before proceeding with fixes.**

### Open questions the run ended on

1. Slot 1 (`issue-236`) still has `fix/236-per-adapter-missing-source` checked out, apparently by another session. Should the fix commits from `polish/237` be pushed straight to the PR branch? That session would then need to pull before committing again.
2. Once fixes are in, full `cargo test` on slot 2 is a multi-minute build (the target is only partly warm). Background, or leave it to the operator?

Neither was answered; this baseline is the review only, with no fixes applied.

# Lens 4: efficiency — PR #237 (`fix(sync): fail the adapter, not the run, when a source dir is absent`)

Reviewed `.bernstein-pr.diff` (3295 lines, 15 files) and `.bernstein-pr.md` in full; the
checkout is base `d475b2b` (the PR is not applied here), so base-side line numbers below
are the lines I actually read, and PR-side numbers are counted from the diff hunks.

Verdict from this lens: the diff's one structural performance change is a **win** (an
all-absent whole-config sync now returns before `open_store` and before the
`LazyEmbedder::candle()` cold-load — both live in `run_sync_stages`, `main.rs:4126` and
`main.rs:4134-4168`, which the new short-circuit in `run_sync` skips). It also removes a
dead counter (`IngestSummary::storage_errors`). One finding: `pond status` gained new
blocking work on the branch that used to be config-only.

---

## Finding L4-1 — `local_status` newly runs the full adapter enumeration on the never-initialized `pond status` path, and part of that work cannot pay off

**identifier:** `local_status`
**category:** efficiency
**severity:** minor
**impact:** none (cost only — no correctness, security or deploy consequence)
**file:line:** `packages/pond/src/main.rs:1301-1302` (PR side, hunk `@@ -1294,22 +1294,36 @@`),
inserted directly under the base guard `packages/pond/src/main.rs:1296`
`if !store.initialized().await? {`

### Claim

The `Command::Status` arm's never-initialized branch used to read config only. The PR
replaces that with a call to `local_status`, which walks **every configured adapter's
source tree** — and on this branch it can only ever take the expensive arm, because the
freshness-map read it uses first is provably wasted here. The added comment at PR-side
`main.rs:1297-1300` reads "The local rows cost no store read", which understates what the
call does.

### Evidence (all lines read)

The new call site (PR side, immediately under the base guard at `main.rs:1296`):

```rust
                // The local rows cost no store read, and an all-absent sync
                // now leaves the store uninitialized - so this branch has to
                // carry them, or the host this PR is about loses the only
                // surface that names its missing sources.
                let local =
                    local_status(&loaded, &store, &store_key, crate::schedule::status_snapshot()).await;
```

What `local_status` then does per adapter (base `main.rs:6283-6336`; the PR keeps this body
and only adds the absent-root arm ahead of it):

```rust
    let rowmap = store.open_cached_rowmap(&default_cache_dir()).await;   // main.rs:6283
    let pending_known = rowmap.is_some();                                // main.rs:6284
...
    for entry in resolved {                                              // main.rs:6291  (sequential)
...
        let plan = if pending_known {
            opened.plan(&oracle).await.ok().flatten()
        } else {
            None
        };                                                               // main.rs:6312-6316
        let (sessions, error) = match &plan {
            Some(plan) => (Some(plan.sessions), None),
            None => match opened.discover().await {                      // main.rs:6319
```

`open_cached_rowmap` ends in a store round trip, not a config read
(`packages/pond/src/sessions.rs:2003-2014`):

```rust
    pub async fn open_cached_rowmap(&self, cache_dir: &Path) -> Option<Arc<RowMetaSet>> {
        let chain = discover_chain(cache_dir, &self.store_key())?;
        let set = RowMetaSet::open(&chain).ok()?;
        let live = self.handle.dataset(Table::Messages).await.ok()?;
        if set.len() > live.count_rows(None).await.ok()? {
```

`Store::initialized` (`packages/pond/src/substrate.rs:2914-2926`) is a
`describe_table` on `sessions::PARTS`; a store that answers `false` there has no messages
dataset either, so `self.handle.dataset(Table::Messages).await.ok()?` is where
`open_cached_rowmap` bails. **On the `!initialized()` branch the function can only return
`None`** — after reading the cached chain segments off disk (`RowMetaSet::open`,
`sessions.rs:2005`) and after one attempted dataset open against the destination (a network
round trip on `s3://`/`gs://`). And because it returns `None`, `pending_known` is `false`,
so the `plan()` arm is dead on this branch and `discover()` at `main.rs:6319` runs for
**every** adapter that has a source present.

`discover()` for the jsonl adapters is a full recursive walk of the configured root
(`packages/pond/src/adapter/jsonl.rs:205-222` → `collect_tree_files`,
`jsonl.rs:180-203`, `std::fs::read_dir` on every directory, then a sort of every path),
sequentially per adapter. The PR does *not* change that cost for absent sources — its new
`missing_source_root` arm in `local_status` short-circuits those before `factory.open`,
which is a saving — but for a source that **exists** (the ordinary fresh install:
`pond init` done, first `pond sync` not yet run) it is all new.

Measured on base, installed `pond 0.17.3`, with
`[adapters.claude-code].path = $T/src` holding 300 session files and no store:

```
$ strace -f -e trace=openat,getdents64 -o base.log pond status      # store uninitialized
  opens against $T/src : 0        getdents64 total : 8   (none under the source tree)
$ strace -f -e trace=openat,getdents64 -o dry.log pond sync --dry-run   # same tree, enumerated
  opens against $T/src : 2  ($T/src, $T/src/project-a)   plan claude-code  300 sessions
```

i.e. base `pond status` never opens the configured source tree; the PR's branch now opens
it once per directory per adapter, on every `pond status` until the first sync.

The same call also drags the scheduler probe into the `--format json` path, which carried
no `schedule` block before (`status_json_empty`, base `main.rs:5916`):
`status_snapshot()` → `platform_probe()` → `unix::probe()` (`schedule.rs:173-174`,
`schedule.rs:387-401`) → `Command::new("systemctl")` (`schedule.rs:461-468`), or
`id -u` + `launchctl` on macOS (`schedule.rs:624-651`). That one is deliberate — the new
document has a `schedule` key — but it is a fork/exec added to a previously config-only
exit, so it belongs in the accounting.

Why this matters more here than elsewhere in this command: the sibling branch documents the
opposite priority (`main.rs:1322-1326`) —

```
                // Default status never scans the 2M-row `messages` table:
                // totals come from manifest metadata (`row_counts`), adapter
                // count from a scan of the small `sessions` table, and the
                // embedding probe (which DOES scan messages) only runs under
                // `-v`. Skipping it drops a cold-S3 status from ~43s to ~3s.
```

— and the motivating case for this change (a host whose every source is absent) is already
served by the cheap arms: the new `missing_source_root` row plus
`syncstate::read_last_sync`, which is exactly what the new integration test
`status_names_absent_sources_on_a_host_that_never_stored_anything` asserts.

### Suggested direction (question, not a fix)

- Could `local_status` skip `store.open_cached_rowmap(...)` on this call? On the
  `!initialized()` branch it cannot return `Some`, so the chain read plus the dataset
  attempt is dead work and `pending_known` is `false` by construction — passing
  `&pond::adapter::NoopOracle` (already used at `main.rs:4813`) or a flag would make that
  explicit rather than incidental.
- If the session counts for *readable* sources stay on this screen, is it worth fanning the
  per-adapter work out instead of awaiting it one adapter at a time —
  `futures::future::try_join_all` is already the codebase's tool for exactly this
  (`packages/pond/src/handlers.rs:769`, `packages/pond/src/handlers.rs:1802`), and each
  adapter's `discover()` is an independent `spawn_blocking`.
- Minor, same block: `let has_adapters = match loaded.resolve_adapters(None)` (PR-side
  `main.rs:1303`) re-resolves what `local_status` just resolved a line earlier at
  `main.rs:6287` and already stored in `local.adapters_error`. `local.adapters` (or the
  already-computed `all_sources_missing`) looks like it carries the same answer.

### Checks a reviewer can run

- `git show d475b2b:packages/pond/src/main.rs | sed -n '1296,1320p'` — the base branch calls
  only `loaded.resolve_adapters(None)`; no `local_status`.
- `grep -n "open_cached_rowmap\|pending_known\|discover()" packages/pond/src/main.rs` inside
  `local_status` (`main.rs:6283`, `6284`, `6319`) plus `substrate.rs:2914` `initialized` —
  establishes that `plan()` is unreachable on the never-initialized call.
- The strace pair above: `0` vs `≥1` opens against the configured source dir is the whole
  delta, and it scales with the size of the operator's transcript trees.

---

## Considered and deliberately not filed

- **Repeated `resolve_sync_adapters` per run.** The PR adds one more whole-config resolve in
  `run_sync`'s all-absent block (result discarded unless every root is absent) and one more
  in the narrowed pre-check, on top of `run_import_stage` and the pre-existing
  `openclaw_in_scope` resolve (`main.rs:4426`). `Config::resolve_adapters`
  (`config.rs:696-731`) is pure in-memory work over already-loaded `serde_json` blobs — no
  I/O — so this is microseconds against a run whose `open_store` alone is logged to
  `pond::perf`. Cold path, not filed.
- **`missing_source_root` as a pre-flight existence check.** It is the lens's TOCTOU shape,
  but the cost is 1-3 `stat`s per adapter per run (the run_import_stage re-check is the
  deliberate TOCTOU guard the plan doc names), the failure case is still handled by the
  adapter's own read path, and the plan doc records the reason (`a pre-flight existence
  check, not error-plumbing`, decision 4). Filed nowhere: cost is nil and the choice is
  documented.
- **`deleted_archive_ids` now `dir.is_dir()` + `read_dir`** (openclaw.rs, PR hunk) costs one
  extra `stat` per agent dir per reconcile pass, and it is parity with
  `collect_file_sessions` (`openclaw.rs:3054-3057`), which the comment says on purpose.
- **`store.find_session(&session_id).await?` per `.deleted.` archive id in
  `reconcile_deletions`** (openclaw.rs:3416-3419, one awaited point lookup per archive,
  i.e. an N+1 feeding directly off the changed `deleted_archive_ids` call) — pre-existing
  and out of the changed lines, and already backed by the `sessions_id_btree` scalar index
  (`sessions.rs:4888`), so each lookup is an indexed read. Not a finding; noted so another
  pass does not re-derive it.
- **`SyncStatus::Unimportable { reason } => optional_reason = Some(reason.clone())`**
  (`main.rs`, new arm in `sync_with_progress`) allocates per skipped session, but that
  string is consumed by the per-session `tracing::info!(%reason, ...)` at `main.rs:5491-5501`
  and matches the existing `Skipped`/`Rejected` arms exactly. No new cost.
- **Per-adapter `DegradedAdapter` construction and `IngestSummary::merge` in the import
  loop** — a few `String` clones per adapter per run, each guarded by
  `if self.first_*.is_none()`. Noise next to the store work in the same loop.
- **`failed_adapters` / `degraded_adapters` growth** — bounded by adapter count,
  `drop_reasons` is a `BTreeMap<&'static str, usize>` over the `DROP_REASON_*` constants.
  No unbounded structure introduced, no new listener or long-lived task.

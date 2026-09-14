# Lens 4: Efficiency — review findings

PR: "fix(sync): fail the adapter, not the run, when a source dir is absent" (#237)
Diff: `.bernstein-pr.diff` (3 295 lines: ~970 src + spec/plan docs + ~1 350 new integration tests)
Base: `d475b2b` (this worktree's HEAD; the PR head is **not** applied here)
Reviewer: lens-4-efficiency-aa4bbaa3 · no repository file modified, nothing committed, nothing pushed

## How I read it (method, so the citations can be re-checked)

The checkout is at base and the patch does not touch it (`git status`: clean). To read the
post-change functions rather than reconstruct them from hunk context, I copied the tree to
`/tmp/pr237-head` (outside every repository) and applied `.bernstein-pr.diff` there with
plain `git apply`. **All `main.rs:`, `handlers.rs:`, `openclaw.rs:` post-change line numbers
below are from that scratch copy**; every "base" citation is from this worktree at
`d475b2b`. Nothing was written into the worktree.

I ran **no** build, lint or test command. Nothing I claim needed one: every finding below is
a call-graph / syscall / allocation argument read from source, and the PR's own verification
commands live in its own tree (which I must not validate against). Where a cost is
quantitative I quote the repo's own measured numbers instead of inventing mine.

**Net read:** the PR's headline efficiency move is good and correctly placed — an
all-absent whole-config sync now returns before `open_store(..., true, ...)`
(`main.rs:4353`, which creates the destination) and before the ~500 MB embedder cold-load
(`main.rs:4362-4390`), while a narrowed invocation fails ahead of the flock at
`main.rs:4038`. It also deletes a genuinely dead counter (see "credited wins"). The findings
are about cost this PR adds **elsewhere** — on `pond status`, in the reporting path inside the
ingest loop, and in duplicated resolve/stat work — none of which the PR body measures.

---

## F1 — `pond status` on an uninitialized store now does a full source enumeration per adapter, and a subprocess probe in the JSON path
**Severity: medium · confidence: high (call graph verified end to end)**
`main.rs:1296-1302` (new) · `main.rs:6880-6882`, `main.rs:6924-6939` · base `main.rs:1296-1316`

Base's never-synced branch touched **no adapter source at all** and ran the scheduler probe
**only in the Text arm**:

```rust
// base main.rs:1296-1312
if !store.initialized().await? {
    let (has_adapters, adapters_error) = match loaded.resolve_adapters(None) { ... };
    match format {
        Json => output(&status_json_empty(&resolved, adapters_error.as_deref())?)?,
        Text => { render_empty_status(...)?; output(&crate::schedule::status_line())?; ... }
```

The PR replaces that with `local_status(...)` for **both** formats (`main.rs:1301-1302`).
Inside `local_status`, for an uninitialized store the freshness oracle is guaranteed absent
— `open_cached_rowmap` (`sessions.rs:2003-2015`) bails at `self.handle.dataset(...).await.ok()?`
because there is no dataset — so `pending_known` is false, `plan` is skipped
(`main.rs:6924-6928`), and **every** enabled adapter falls to `opened.discover().await`
(`main.rs:6931`). What `discover()` actually costs per adapter:

- jsonl-family adapters (claude-code, codex-cli, nanoclaw, grok, agy, …):
  `jsonl_tree_discover` (`jsonl.rs:205-222`) → `collect_tree_files` (`jsonl.rs:180-203`) — a
  full recursive `read_dir` with a `file_type()` per entry, accumulating `Vec<PathBuf>` of
  every transcript, purely to `count()` them, in a `spawn_blocking`.
- `openclaw`: `discover()` (`openclaw.rs:268-288`) → `enumerate_and_peek` (`openclaw.rs:459+`)
  — `list_agents`, `open_db` **per agent**, `list_db_sessions`, plus
  `collect_file_sessions` (`openclaw.rs:3049-3079`), which reads and parses each agent's
  `sessions.json`.
- sqlite-backed adapters open their DBs.

So the pre-first-sync `pond status` goes from "read nothing outside the store" to "walk every
configured transcript tree and open every adapter DB", **serialized** across adapters. The
repo is explicitly sensitive to exactly this class of cost on this command — base
`main.rs:1320-1327`: *"Default status never scans the 2M-row `messages` table … Skipping it
drops a cold-S3 status from ~43s to ~3s"* — and it has measured corpus sizes in the
thousands of files (`jsonl.rs:243-245`: *"a ~9k-file corpus"*). This new cost is the one that
scales with the user's corpus, on the host with the **biggest** corpus-per-dollar-of-value
(a fresh install about to run its first sync), and on fleet hosts whose home is a network
mount.

The new comment understates it: *"The local rows cost no store read"* (`main.rs:1298-1300`) is
true and irrelevant — the rows cost a **source** read.

Second, smaller half of the same change: the JSON never-synced document gains a `schedule`
key, which requires `crate::schedule::status_snapshot()` — up to **two synchronous subprocess
spawns** on Linux (`schedule.rs:170-171` → `platform_probe` → `systemd_timer_enabled()`
running `systemctl --user is-enabled` at `schedule.rs:458-466`, then `read_cron_fence_entry()`
at `schedule.rs:928-930` reading `crontab`), one `id -u` spawn on macOS (`schedule.rs:643-651`).
Base never spawned on this path for `--format json` (`status_line()` was Text-only), and the
call is inline in an `async fn`, not `spawn_blocking`. `pond status --format json` is the
agent-facing surface, so that's the path where an added spawn costs a round-trip in the
worst place.

Who hits it: a fresh install before the first sync; `pond status --storage-path <new dest>`;
the all-absent fleet host until `open_store` materializes the store on its first status. Note
the fleet case is the *cheap* one — `missing_source_root` short-circuits each adapter before
`factory.open` (`main.rs:6892-6903`), which is a real saving and the right shape. The
expensive shape is precisely "sources present, store absent".

Fix, cheapest first:
1. In the never-synced branch, render the adapter rows **without** enumerating — null
   `sessions`, no `plan` — which the codebase already knows how to draw: the null arms are
   `main.rs:6998-7011` and the count arms only fire on `Some` (`main.rs:7012-7027`). Keep the
   existing "(pending-sync counts appear after the first `pond sync`)" line.
   The information this PR is actually about — the `reason: "source_missing"` token — needs
   the stat, not the walk.
2. If the counts are wanted there, enumerate concurrently and bounded (see F2), or gate the
   walk behind `-v` / a flag, and say so in the 7.8 status sentence you are already editing.
3. Drop the probe from the JSON never-synced document, or run it in `spawn_blocking` and only
   when `format` needs it.

## F2 — per-adapter enumeration is awaited sequentially, so F1's cost is the sum, not the max
**Severity: low-medium · confidence: high**
`main.rs:6888-6949` (loop), `main.rs:6931` (`opened.discover().await`) · base `main.rs:1360` (precedent)

`local_status` walks `resolved` in a `for` loop and awaits `plan()`/`discover()` inside it.
Each `discover()` is an independent `tokio::task::spawn_blocking`, so N adapters means N
serialized blocking-pool round trips; total latency is the sum of every adapter's walk. The
same command already fans its independent work out with `tokio::try_join!` over seven store
reads (base `main.rs:1352-1363`), so the pattern is house style — it just stops at the
adapter loop. This is pre-existing on the initialized path, but F1 makes it newly
load-bearing: before this PR, the never-synced host paid none of it. `futures::future::join_all`
over the adapter futures (or a `buffer_unbounded`-style bounded join) turns F1's sum into a
max; the ordering of the resulting rows is already handled — rendering derives `labels` from
`local.adapters` order (`main.rs:6979-6989`), so collect into a Vec and keep input order.

## F3 — a report line written inside the ingest loop can end the run, exit 0, and lose the breadcrumb
**Severity: medium · confidence: high for the mechanism, medium for the trigger**
`main.rs:5248`, `main.rs:5277` (`emit_source_missing`/`emit_degraded`, both `?`) →
`main.rs:5319-5324` `paint_err_above` → `main.rs:1925-1927` `output_err` → `lib.rs:120-126`

```rust
// lib.rs:120-126 (base, unchanged)
match writeln!(stderr, "{message}") {
    Err(error) if error.kind() == io::ErrorKind::BrokenPipe => std::process::exit(0),
    result => result.context("failed to write command meta"),
}
```

The PR puts two new calls to this helper **inside the per-adapter loop**, and propagates their
`Result` with `?`. Consequences, in order of nastiness:

- **BrokenPipe → `std::process::exit(0)` mid-sync.** `pond sync 2>&1 | head -1`, a logging
  wrapper that closes early, a rotating-pipe harness: the process dies at the *warning* line,
  with `run_sync`'s `write_last_sync` never reached and no summary document on stdout — and
  exit **0**, so the cron/journal record looks like a clean run. That is the same silence
  class this PR exists to eliminate, reached through the reporting path.
- **Any other stderr error → `?` out of the loop**, so the adapters after this one never run.
  The design promise in the spec sentence this PR adds is "the run continues"; an I/O failure
  on a *reporting* surface now overrides it.

The repo's own convention for a write inside this loop is the opposite:
`let _ = mp.println(format_sync_line(...))` (`main.rs:6035`) — in-loop progress lines ignore
errors deliberately. The counts are already safe (the PR merges before emitting, at
`main.rs:5245-5248` and `main.rs:5260`/`5275-5277`, which is good and worth keeping); it's the run
that isn't. Fix: `let _ =` on both emissions (they are reports, not results), or route a
failure to `tracing::debug!`. The hazard lives in `line_err`, which this PR doesn't touch, but
the PR is what moves it inside the loop and what makes the run's continuation depend on it.

## F4 — the adapter set is resolved and stat'd two-to-three times per run, and twice per never-synced status
**Severity: low · confidence: high**
`main.rs:4038-4049`, `main.rs:4119-4131`, `main.rs:5155`, `main.rs:5160`, `main.rs:5212`, `main.rs:5236` · `main.rs:1303` vs `main.rs:6884` · `config.rs:696-731`

`resolve_sync_adapters` now runs twice on every real sync path (once in `run_sync`'s
narrowed pre-check or all-absent gate, again in `run_import_stage`), and the resolved set is
`try_exists()`-stat'd up to three times per adapter: the all-absent gate
(`main.rs:4121-4128`), the first-sync notice's `.all()` conjunct (`main.rs:5212`), and the
per-adapter pre-flight (`main.rs:5236`). `pond status` likewise resolves twice: once inside
`local_status` (`main.rs:6884`) and once for `has_adapters` (`main.rs:1303`).

Cost in isolation is small — `resolve_adapters` (`config.rs:696-731`) is in-memory (blob
clones + the dup-path scan, no IO), and a stat is a stat. Why it's still worth one refactor:
the three sites must agree about what "resolved" means for the TOCTOU re-check to mean
anything, `invocation.path.clone()` is repeated per site, and `has_adapters` re-derives
something `local.adapters` + `local.adapters_error` already carry (with the one wrinkle that
`local_status` drops unknown-name entries at `main.rs:6904`). Resolve once in `run_sync`,
pass `&[ResolvedAdapter]` down, and derive `has_adapters` from `local`.

## F5 — TOCTOU double-probe in the openclaw archive scan, and the cheap probe still runs after the DB open
**Severity: low · confidence: high (mechanism), medium (that it matters here)**
`openclaw.rs:3561-3572` (new) · `openclaw.rs:3408-3416` (touched block) · sibling `openclaw.rs:3055-3057`

`deleted_archive_ids` now does `if !dir.is_dir() { return Ok(ids) }` and **then**
`std::fs::read_dir(dir)?`. That is a stat followed by an open where base did one `read_dir`
and swallowed the error — the classic pre-check-then-operate shape: an extra syscall per
agent dir per sync, a window in which the answer can flip, and (the part I'd actually act on)
`is_dir()` returns `false` when the **parent** is unreadable, which classifies a real
permissions problem as "no archives here" — the exact ambiguity the new `Err` arm exists to
surface. The comment claims parity with `collect_file_sessions`, and it is right that the
sibling uses the same `is_dir()` probe (`openclaw.rs:3055-3057`), so this is house style and I
am not asking for a one-off deviation — but "same tolerated set" is a claim about the two
readers, and the honest version of the comment is "tolerates the same set *including* an
unreadable parent, which it reports as empty".

Adjacent, and inside the block this PR edits: the dir probe runs *after*
`open_db(...)` + `live_entry_table(conn)` (`openclaw.rs:3408-3413`), so every agent pays a
SQLite open plus an entry-table scan per sync before the code knows whether that agent has a
single `.deleted.` archive — which for most agents is none, and the loop at
`openclaw.rs:3423` then does nothing. Hoisting `deleted_archive_ids` above the DB open (plus
an early `if deleted.is_empty() { continue }`) removes a DB open and a table scan per agent
per run, and puts the cheap probe first so the new `continue` never wastes the expensive one.

## F6 — the new attribution lines have no change detection: the same line, forever, at the default 5-minute cadence
**Severity: low · confidence: high**
`main.rs:5302-5317` (`emit_source_missing`) · `main.rs:5286-5298` (`emit_degraded`) ·
`schedule.rs:72,77` (5m default) · `schedule.rs:819` (`>> sync.log 2>&1`)

A fleet host with N absent adapters prints N identical red lines on every run, unconditionally,
with no comparison against the previous run's verdict. At the documented default cadence that
is ~288 ticks/day × N lines, appended to `sync.log` by the cron entry (`schedule.rs:819`);
nothing in-tree rotates that file. `-q` does not gate it: the CLI arm writes through
`output_err` directly rather than through `tracing` (`main.rs:5302-5317`), so the quiet flag
that the scheduler itself passes has no effect on these lines. In-serve mode is the same on
`warn` (`main.rs:5293`, `main.rs:5308`) unless the filter is above warn.

I recognize the PR body's reasoning — cron logs must carry attribution — so this is a
cost-with-a-cheap-fix, not a defect: the last-sync record is read on the very next `status`
call, so it could carry the failed-set and the run could print only on a change (or drop to
`debug` when the set is unchanged since the last breadcrumb). Log growth is unbounded
otherwise, and a permanent condition looks identical to a fresh one.

---

## Nits (fix if the file is open anyway; not worth a round trip on their own)

- **`main.rs:5261-5270`** — a `DegradedAdapter` is built for **every** adapter pass (name
  clone, `adapter_label` String, `source_path` Option<String>, two reason clones) and then
  discarded when `summary_line()` returns `None`, i.e. on every healthy pass. Compute
  `summary_line()` from the summary first, construct the struct only when it's `Some`. Bounded
  by adapter count, so this is cosmetic — but the healthy path is the common one.
- **`handlers.rs:434-444`** — the pre-session skip path now allocates `error.to_string()`
  twice per skipped file (once for `first_skip_reason`, once for `SyncStatus::Skipped
  { reason }`). One `String`, one clone from it.
- **`handlers.rs:419-427`** — `first_unreadable_reason` retains a second copy of a string the
  in-flight slot already holds in `first_drop_reason`. Bounded (one per summary) and the
  rename rationale in the PR body is sound; noting only that it is duplicate retention, and
  that the `is_none()` guards correctly keep the per-event path allocation-free once set —
  which is the thing that matters in a loop that the repo has measured at tens of thousands
  of drops.
- **`main.rs:6016-6020`** — `SyncStatus::Unimportable { reason } => optional_reason =
  Some(reason.clone())`: the clone is skipped by the scroll-back `println` (the `!matches!`
  at `main.rs:6027-6034` excludes it) and survives only for the `tracing::info!` arm, which is
  off by default at `WarnLevel`. A String clone per contract-excluded session per run. Matches
  the existing `Skipped`/`Rejected` arms, so consistency argues to leave it.

## Credited wins (read, not asserted — these are the PR getting it right)

- **`main.rs:4110-4170`** — the all-absent short-circuit sits after the flock and before
  `open_store(..., true, ...)` (`main.rs:4353`) and the embedder cold-load with its ~500 MB
  model read (`main.rs:4362-4390`). On the host this PR is about, that is the difference
  between a cron tick that does nothing and one that cold-loads a model to do nothing. The
  placement trade (keep the lock, skip the store) is the right one and the reasoning in the
  plan doc holds up against the code.
- **`main.rs:4038-4049`** — the narrowed pre-scan runs ahead of the flock wait, store
  creation and model load, so a failing `pond sync <adapter>` no longer creates a destination
  it never uses.
- **`sessions.rs:3803/3898` (base) removed** — I verified `storage_errors` had **no write
  site** anywhere on base (`grep -rn storage_errors` → the field declaration, `merge`, and two
  test reads). Deleting it removes a counter incremented nowhere and a JSON key no run could
  emit. Removing the dead field beats shipping a health key that is always zero.
- **`schedule.rs:166-171` (`status_line()`) deleted** — collapses a second probe into the one
  `status_snapshot()` the caller already passes to `local_status` on the Text path.
- **`main.rs:4461-4471`** — when openclaw is in `failed_adapters` or `degraded_adapters`, the
  reconciliation pass is skipped instead of re-walking a root that just failed to read.
- **`main.rs:6892-6903`** — status's absent-root short-circuit lands *before* `factory.open`
  and `discover()`, so a fleet host's status costs one stat per adapter rather than a walk.
  This is the shape F1 should have used everywhere.

## Lens bullets that produced nothing, for coverage

- **Memory / unbounded structures / listener leaks**: both new vectors (`failed_adapters`,
  `degraded_adapters`) are bounded by resolved-pass count and gated by `summary_line()`;
  `drop_reasons` is a `BTreeMap<&'static str, _>` bounded by the fixed `DROP_REASON_*` key
  set; `SyncReport` holds one `IngestSummary` where it held two `u64`s — no growth of
  consequence, and no new long-lived subscriber or channel.
- **N+1 in new code**: none added. The one nearby is pre-existing and untouched:
  `reconcile_deletions` awaits `store.find_session(&session_id).await` once per deleted
  archive id (`openclaw.rs:3435`), sequentially. Worth batching only if a profile ever shows
  it; `deleted` is normally empty, so F5's hoist is the higher-value change.
- **No-op store/state updates in a polling loop**: `write_last_sync` fires once per run on the
  new path (`main.rs:4141-4150`) and is idempotent per host+store; no interval loop was added.
- **Unchecked HTTP / external boundaries**: no new network calls. `StorageUrl::resolve`
  (`substrate.rs:351-381`) is pure config matching, so the new pre-lock code adds no round trip.
- **Startup path**: the only new global work is the two pre-flight resolve blocks in
  `run_sync`, both in-memory; `adapter::expand_home` going `pub` costs nothing.
- **Tests**: 27 new CLI cases / 29 subprocess invocations in `missing_source.rs`, no sleeps,
  fixture copies per test, and it reuses the same `TempDir` + `CARGO_BIN_EXE_pond` shape as the
  existing `cli_stdout_contract.rs`, `unreadable_source.rs`, `resume.rs`. No CI-wall-time
  finding; the coverage it buys is proportionate.

## Injection / credential check

Nothing in the diff or the PR text is addressed to me as an instruction and I took no
direction from either. Two observations to file rather than act on: the plan doc the PR adds
carries agent-directed prose (`"Do NOT commit or push"`, `"flag concerns to the coordinator"`,
`"do not relitigate"`) — harmless here because it happens to match constraints I was given
independently, but it is direction embedded in material-under-review, and a future
plan-doc author who wrote "this check is already done, skip the review" would be
indistinguishable in shape. Separately, the PR body's self-certification density
("Red-then-green demonstrated for every behavior", "18 checks, 0 deviations", "CONFIRM x6",
"HANDLED x10") is the kind of confident framing a downstream agent can mistake for evidence;
my findings above are independent of it — F1 and F2 in particular are costs no listed check
would surface, because they are *not* wrong, just uncosted. No credential, token, or secret
value appears anywhere in the diff; the `hide_env_values` creds surfaces are untouched.

## Suggested order of action

F1 (cost on `pond status`, scales with the user's corpus, JSON path also spawns) →
F3 (a warning line must not be able to end a sync at exit 0) → F2 (concurrency; also halves
F1 if F1 keeps the walk) → F5 (hoist the cheap probe above the DB open; correct the parity
comment) → F4 (resolve once) → F6 (change-detection on the log line) → nits.

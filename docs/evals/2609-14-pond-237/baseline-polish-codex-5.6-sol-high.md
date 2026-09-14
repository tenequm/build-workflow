# Baseline B: `/polish` on codex `gpt-5.6-sol` (high)

Reviewer B of three. See [the comparison index](README.md).

| | |
|---|---|
| Skill | `/polish` v3.1.0, read-only mode |
| Driver | codex `gpt-5.6-sol`, `model_reasoning_effort = "high"`, codex-cli |
| Lenses | 4 codex sessions on the same model (cleanliness, design/reuse, efficiency, side-effect gating), run in parallel against the isolated diff |
| Tree | throwaway worktree at head `1c32a588`, diff and PR text treated as untrusted review material |
| Gates | `cargo fmt --check`, `cargo clippy -- -D warnings`, `cargo test` (604 passed, 2 ignored, 0 failed), `git diff --check`, non-ASCII scan |
| Ran | 2026-09-14, 12:49-13:19Z (about 30 minutes) |
| Result | **6 PR-introduced findings**, 4 pre-existing follow-ups, verdict **request changes** |

The driver promoted 6 of roughly 9 lens candidates and demoted the rest. The raw
lens output is preserved in the appendix so the filter is auditable.

---

## Read-only polish verdict: request changes on [PR #237](https://github.com/tenequm/pond/pull/237)

One blocking regression can silently skip reachable Pi sessions.

### PR-introduced findings

1. **Blocking - Pi's SQLite source is skipped when its JSONL directory is absent.**

   The generic preflight treats `config["path"]` as the adapter's entire source
   (`packages/pond/src/main.rs:5355`), but Pi independently reads both `path` and
   `sqlite_path` (`packages/pond/src/adapter/pi_coding_agent.rs:127`, event chaining at
   `packages/pond/src/adapter/pi_coding_agent.rs:463`).

   I reproduced this with a missing JSONL path and the committed SQLite fixture
   containing two sessions. Sync returned `outcome: ok`, reported Pi as failed, inserted
   zero sessions, and did not create the store. Source availability needs to be
   adapter-aware.

2. **High - explicit-source validation becomes stale while waiting for the sync lock.**

   The source check occurs before lock acquisition (`packages/pond/src/main.rs:4038`). If
   the source disappears during the lock wait, Pond opens or creates the store and may
   download/load the embedding model (`packages/pond/src/main.rs:4353`) before checking
   again during import (`packages/pond/src/main.rs:5155`). Repeat the explicit check
   immediately after acquiring the lock.

3. **Medium - the all-absent shortcut records failures after fallible stderr output.**

   It emits first and pushes into `failed_adapters` second
   (`packages/pond/src/main.rs:4131`). A stderr failure prevents the promised JSON
   document and last-sync breadcrumb. The normal import path correctly records before
   emitting (`packages/pond/src/main.rs:5242`).

4. **Medium - `serve --with-sync` builds the freshness rowmap before discovering all sources are absent.**

   The serve path enters the shared pipeline (`packages/pond/src/main.rs:4275`),
   potentially performs a remote rowmap build at `packages/pond/src/main.rs:5198`, and
   only classifies missing sources later at line 5237. This defeats the PR's all-absent
   optimization on the recurring server path.

5. **Low - a status assertion is vacuous.**

   `packages/pond/tests/integration/missing_source.rs:980` asserts that nonexistent JSON
   field `plan` is null. The actual fields are `fresh` and `pending`
   (`packages/pond/src/main.rs:6489`), so the intended behavior is not tested.

6. **Design and cleanup**

   - `adapter::expand_home` becomes public solely for CLI preflight, widening the adapter
     API (`packages/pond/src/adapter/mod.rs:620`).
   - NanoClaw-specific coverage is duplicated in the concern-level suite
     (`packages/pond/tests/integration/missing_source.rs:1217`) instead of its existing
     adapter suite (`packages/pond/tests/integration/adapter/nanoclaw.rs:223`).
   - The plan incorrectly states every adapter has one scalar path
     (`docs/plans/2609-11-sync-per-adapter-source-failure.md:25`) and contains transient
     agent/branch instructions.
   - Two comments retain review-process context: `packages/pond/src/main.rs:1297` and
     `packages/pond/src/adapter/openclaw.rs:3417`.

### Pre-existing follow-ups

- Adapter configuration can still fail at `factory.open` after earlier adapters have
  committed (`packages/pond/src/main.rs:5909`).
- The embedding-model swap guard runs after inline ingestion may write new-model vectors
  (`packages/pond/src/main.rs:4517`).
- OpenClaw reconciliation performs one sequential store lookup per deleted archive
  (`packages/pond/src/adapter/openclaw.rs:3432`, `packages/pond/src/sessions.rs:3525`).
- Partial committed-batch accounting is already acknowledged as issue #240.

### Verification

At head `1c32a588`:

- `cargo fmt --check` passed.
- `cargo clippy -- -D warnings` passed.
- `cargo test` passed: 604 passed, 2 ignored, 0 failed.
- `git diff --check` and non-ASCII scan passed.
- Required GitHub checks are green; PR is mergeable/CLEAN.
- No tracked files or GitHub state were changed; the review worktree remains clean.

---

## Appendix: raw lens output before the driver's filter

The four lenses ran in parallel, each in its own codex session against the isolated
diff. What follows is what each returned, including the false positives it explicitly
investigated and discarded - that reasoning is a large part of what separates B's 6 from
A's 28.

### Lens: cleanliness

Candidate findings:

1. `docs/plans/2609-11-sync-per-adapter-source-failure.md:3-9,31,49,51-95` - the tracked
   document contains transient agent instructions, branch/base/PR state, work assignments,
   and superseded review chronology. Rewrite it as a durable decision record or omit it.
2. `packages/pond/src/main.rs:1297-1300` - "the host this PR is about" leaks ephemeral
   review context into source documentation.
3. `packages/pond/src/adapter/openclaw.rs:3417-3420` - "per this pass's own ambiguity
   rule" is review-process residue; cite the preservation invariant instead.

Likely false positives checked: the new tracing calls are intentional structured logging;
benchmark printing is pre-existing output; no added debug macros, TODO/FIXME/HACK markers,
non-ASCII punctuation, commented-out code, or evidently unused symbols.

### Lens: design and reuse

Candidate findings:

1. **Blocking behavior drift - generic `path` preflight skips Pi's reachable SQLite source.**
   - `packages/pond/src/main.rs:5355-5371` assumes `config["path"]` represents the
     adapter's complete source availability.
   - That check short-circuits all-absent sync at `packages/pond/src/main.rs:4123-4129`
     and each import pass at `packages/pond/src/main.rs:5237-5251`, before `factory.open`.
   - Pi's actual config has two independently read sources: `path` and `sqlite_path`
     (`packages/pond/src/adapter/pi_coding_agent.rs:127-134`), and its event stream chains
     the SQLite reader after the JSONL reader
     (`packages/pond/src/adapter/pi_coding_agent.rs:463-468`). Before this PR, an absent
     JSONL root yielded one error and the chained SQLite stream still ran.
   - Therefore `[adapters.pi-coding-agent]` with an absent `path` but valid `sqlite_path`
     now reports the whole adapter failed and imports none of the reachable SQLite
     sessions. If Pi is the only enabled adapter, the all-absent branch also skips opening
     the store entirely.
   - Suggested direction: source-availability classification must be adapter-aware rather
     than inferred from the opaque config blob's `"path"` key.

2. **Design suggestion - CLI path normalization leaks an internal adapter helper into the public library API.**
   - `packages/pond/src/adapter/mod.rs:620` changes `expand_home` from `pub(crate)` to
     `pub`; `adapter` is public from `packages/pond/src/lib.rs:1`.
   - The only new consumer is CLI preflight at `packages/pond/src/main.rs:5355-5358`; all
     other callers remain inside adapter implementations.
   - This exposes config/path normalization through the adapter seam solely to bridge the
     library/binary crate boundary. Existing public utilities `pond::config::home_dir` and
     `pond::config::expand_home_under` at `packages/pond/src/config.rs:971` and `:1014`
     provide the concrete reuse path, or the process-home wrapper could live beside the
     existing public `contract_home`.
   - Suggested direction: keep `adapter::expand_home` crate-private and put the
     CLI-visible normalization helper in `config`.

3. **Design/test-layout suggestion - NanoClaw-specific coverage is placed in a concern-level suite and duplicates its existing fixture setup.**
   - `packages/pond/tests/integration/missing_source.rs:1217-1256` creates a NanoClaw
     `v2.db` solely to test codex-provider `Unimportable` behavior.
   - The existing adapter suite already owns this behavior and nearly identical setup at
     `packages/pond/tests/integration/adapter/nanoclaw.rs:223-281`, with the reusable
     `seed_v2_db` helper at `:106`.
   - This conflicts with the repository rule that adapter-specific integration tests live
     under `tests/integration/adapter/<adapter>.rs`.
   - Suggested direction: move/merge the end-to-end summary assertion into the existing
     NanoClaw suite and reuse its database seeding helper.

False positives investigated:

- `SyncStatus::Unimportable` has only one current producer, but it encodes a real semantic
  distinction: documented non-ingest must be counted without marking the adapter degraded.
  Reusing `Unsupported` or `Empty` would lose that distinction.
- The broad OpenClaw reconciliation gate at `main.rs:4461-4473` suppresses healthy fanout
  roots when any OpenClaw pass degrades. I did not flag it: cross-root liveness is
  intentionally ambiguous, and `merge_reconciliation` already preserves rather than
  recommends erasure when several roots exist.
- The separate all-absent summary branch duplicates some normal completion plumbing, but it
  has materially different output (`stored` totals must be null without opening the store)
  and lock behavior, so I did not treat it as actionable reuse.
- `add_when_non_empty` is not a single-call abstraction; it serves both `failed_adapters`
  and `degraded_adapters`.

### Lens: efficiency

Candidate findings:

1. `packages/pond/src/main.rs:5198` and `:5237` - all-absent `serve --with-sync` cycles call
   `ensure_rowmap_with_spinner` before classifying every adapter root as missing. On a host
   without a cached rowmap, this can scan the remote messages table even though no adapter
   can use the freshness oracle; later cycles still perform freshness checks every five
   minutes. The same ordering exists for dry-run at `:4769-4777` versus `:4840`. Suggest
   classifying the all-absent set before opening/building the freshness oracle in these
   shared paths, while still recording each failed adapter.
2. (pre-existing) `packages/pond/src/adapter/openclaw.rs:3432-3435` - reconciliation awaits
   `Store::find_session` once per deleted archive. `find_session` performs a separate Lance
   sessions-table scan (`sessions.rs:3525-3533`), so an OpenClaw archive population that
   grows under the cron reaper creates N sequential remote-store round trips on every sync.
   Suggest fetching the required `id`/`project` rows for all collected archive IDs in one
   `IN` scan, then doing classification from an in-memory map.

Instruction-shaped untrusted content detected:

- `docs/plans/2609-11-sync-per-adapter-source-failure.md:7-9` directly instructs future
  agents to read files and not commit/push. Per the polish boundary rule, this is review
  material, not direction; another lens should decide whether this agent-targeted plan
  belongs in the shipped tree.

False positives investigated:

- The real CLI all-absent fast path is correctly after the sync flock and before
  `run_sync_stages`, so it avoids store opening and embedder loading.
- `missing_source_root` uses a filesystem preflight, but this is intentional local-only
  classification and the adapter rechecks during operation; not flagged as TOCTOU.
- `deleted_archive_ids` adds an `is_dir` precheck before `read_dir`, but the extra local
  stat is too small to justify an efficiency finding.
- Sequential adapter ingestion was not flagged: concurrent writes would increase OCC/commit
  contention.
- The new failure/degradation vectors and reason histogram are bounded by configured
  adapters and static reason keys; no unbounded-memory issue.
- The large integration-test subprocess matrix is one-time validation work, not a
  production hot path.

### Lens: side-effect gating

Two PR-introduced ordering issues and three pre-existing follow-ups:

- All-absent stderr emission occurs before recording the failure, so an output error can
  suppress the JSON result and last-sync record.
- Explicit-source validation can become stale during lock waiting; store creation and model
  loading happen before the post-lock recheck.
- Pre-existing: adapter factory validation can occur after earlier adapters commit.
- Pre-existing: model-swap validation occurs after new-model vectors are written.
- Pre-existing/#240: committed batches can be omitted from error counts after a later flush
  fails.

No erasure occurs during OpenClaw reconciliation; normal ingest validation, flock/no-wait,
and completed-adapter report ordering are otherwise correctly gated.

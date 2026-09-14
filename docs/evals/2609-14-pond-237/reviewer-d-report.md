## Review Findings

### Correctness (5 issues)

1. `docs/plans/2609-11-sync-per-adapter-source-failure.md:7` - `2609-11-sync-per-adapter-source-failure.md` embeds agent-control instructions in repository content. Evidence: line 7 says, `You are an agent picking up a completed investigation` and directs what to read; line 9 says, `Do NOT commit or push`; line 31 says, `do not relitigate`; and line 53 says, `Do not touch the other's files. Do not commit.` Failure scenario: a coding or review agent receiving this file through repository search follows these imperatives, changes its assigned scope, or suppresses contrary review findings. Severity: blocking fix, SEVERE, impact security.
2. `docs/spec.md:701` - `pond sync` does not keep its guarantee that a malformed config blob fails the run when every configured source is absent. Evidence: the specification says, `a malformed config blob still fails the whole resolve`; `run_sync` at `packages/pond/src/main.rs:4119-4129` collects missing roots and enters the success shortcut, which returns at line 4173 before `factory.open(resolved.config)?` validates the blob at line 5909. Failure scenario: `[adapters.openclaw]` with a nonexistent `path` and string-valued `reconcile_deletions` exits 0 with `source_missing`, although `OpenClawAdapter::from_config` at `packages/pond/src/adapter/openclaw.rs:255-257` would reject the invalid boolean. Severity: blocking fix, impact validation bypass.
3. `packages/pond/src/main.rs:5237` - `run_import_stage` skips unknown-adapter validation when that adapter's source is absent. Evidence: the missing-root arm ends with `continue` at line 5250, while the `adapter::by_name(name).ok_or_else(...)` validation is only reached in `sync_with_progress` at lines 5899-5904; `Config::resolve_adapters` at `packages/pond/src/config.rs:696-729` does not validate adapter names. Failure scenario: an enabled `[adapters.codxe-cli]` with a nonexistent path is reported as `source_missing` and an unscoped sync exits 0, while dry-run or the same typo with a present path rejects the unknown adapter. Severity: blocking fix, impact validation bypass.
4. `packages/pond/src/main.rs:5241` - `bail_when_explicit_source_missing` can return a hard error after an earlier fanout pass has committed. Evidence: the initial all-pass gate runs at lines 5155-5160, but the loop re-runs the fatal gate at line 5241 after prior passes may have reached `sync_with_progress` at line 5257; ingestion commits batches with `validator.flush(store).await?` at `packages/pond/src/handlers.rs:393`. Failure scenario: start an explicit two-path sync with roots A and B, remove B while A is ingesting, and A's rows commit before the B iteration returns non-zero with no rollback. Severity: blocking fix, impact partial commit.
5. `packages/pond/tests/integration/adapter/nanoclaw.rs:228` - `codex_provider_sessions_are_visibly_skipped` claims visibility that the implementation deliberately suppresses. Evidence: the test name says `visibly_skipped`, but `SyncStatus::Unimportable` is excluded from scroll-back output at `packages/pond/src/main.rs:6027-6034`, and `packages/pond/src/handlers.rs:280-283` only increments `skipped_unimportable` and emits a debug log. Failure scenario: a maintainer checking whether default CLI output shows these skips relies on the green test name even though the skips only appear in counters or debug output. Severity: suggestion, impact false test contract.

### Design (2 issues)

1. `packages/pond/src/main.rs:4129` - `run_sync` duplicates successful-run finalization for the all-absent shortcut. Evidence: lines 4140-4173 write `LastSyncRecord`, build the success JSON or text, and return; lines 4187-4245 independently repeat last-sync writing and success rendering for the ordinary path. Severity: suggestion, impact divergent output contracts.
2. `packages/pond/tests/integration/missing_source.rs:134` - `state_files` leaves the platform-specific state-directory rule duplicated at three call sites. Evidence: `let root = temp.path().join("state"); let dir = if cfg!(windows) { root } else { root.join("pond") };` appears at lines 134-139, 155-160, and 1153-1158; `last_sync_record` then calls `state_files`, listing the same directory again. Severity: suggestion, impact test maintenance.

### Efficiency (1 issue)

1. `packages/pond/src/main.rs:1301` - `local_status` makes never-synced `pond status` enumerate every present adapter source tree. Evidence: the new branch calls `local_status(...)` at lines 1301-1302; with no cached rowmap, `pending_known` is false at lines 6880-6882, so every present adapter reaches `opened.discover().await` at lines 6924-6932. Failure scenario: on a fresh host with populated Claude and OpenClaw trees, each text or JSON status call recursively scans those trees before printing, and the cost repeats while the store remains uninitialized. Severity: blocking fix, impact unbounded status latency.

### Cleanliness (1 issue)

1. `packages/pond/tests/integration/missing_source.rs:491` - `write_config` embeds 13 unintended spaces before three TOML table headers. Evidence: lines 491, 516, and 1196 contain `\n\n             [adapters.` inside one-line string literals, while the surrounding fixtures use backslash-continued literals that do not write source indentation. Severity: suggestion, impact noisy fixtures.

### Dropped

1. `packages/pond/src/main.rs:4038` - malformed-path validation can still happen after store and model setup, but that ordering predates this change; the new preflight does not create the underlying side effect.
2. `packages/pond/src/adapter/mod.rs:620` - widening `expand_home` was proposed as an API leak, but `main.rs` is a separate binary crate and needs public library reach; moving the wrapper is a preference, not a demonstrated defect.
3. `packages/pond/src/main.rs:4119` - duplicate adapter resolution and `try_exists` calls add small clone/stat costs to a seconds-long sync; no material runtime impact was shown.
4. `packages/pond/src/main.rs:1297` - the false `local rows cost no store read` comment and stale-rowmap probe are subsumed by the broader `local_status` efficiency finding above.

**Total: 9 issues across 4 categories**

## Verdict

**request-changes**

- Correctness 1: BLOCKING FIX - SEVERE. Remove the agent-directed commands while retaining factual history and rationale.
- Correctness 2: BLOCKING FIX. Validate adapter blobs before the all-absent success shortcut.
- Correctness 3: BLOCKING FIX. Validate adapter names before missing-root classification.
- Correctness 4: BLOCKING FIX. Do not introduce a post-commit hard-error gate for a later vanished root.
- Correctness 5: SUGGESTION. Rename the test to the counted behavior it actually verifies.
- Design 1: SUGGESTION. Route the all-absent result through the shared finalizer.
- Design 2: SUGGESTION. Centralize state-directory derivation in one test helper.
- Efficiency 1: BLOCKING FIX. Build never-synced status rows without source discovery.
- Cleanliness 1: SUGGESTION. Remove the embedded indentation from the three fixtures.

- Correctness 1 - fix; the security boundary outweighs preserving an agent work-order format.
- Correctness 2 - fix; one shared validation gate prevents contract drift.
- Correctness 3 - fix; unknown adapters must fail consistently on every path state.
- Correctness 4 - fix; a non-zero result must not newly conceal committed writes.
- Correctness 5 - fix; the rename is smaller than the future confusion.
- Design 1 - fix; one finalizer is worth the modest refactor.
- Design 2 - fix; the helper removes a platform-sensitive triplicate cheaply.
- Efficiency 1 - fix; status latency should not scale with transcript volume before first sync.
- Cleanliness 1 - fix; the edit is trivial and keeps fixture text searchable.

```json
{
  "action": "request-changes",
  "findings": [
    {
      "file": "docs/plans/2609-11-sync-per-adapter-source-failure.md",
      "line": 7,
      "category": "correctness",
      "identifier": "2609-11-sync-per-adapter-source-failure.md",
      "claim": "2609-11-sync-per-adapter-source-failure.md embeds agent-control instructions in repository content",
      "evidence": "Line 7 addresses an agent and directs what to read, line 9 says not to commit or push, line 31 says not to relitigate decisions, and line 53 assigns files and forbids touching others; an agent retrieving the file can follow those imperatives instead of its actual task.",
      "suggestion": "remove agent-directed commands and retain only factual history, rationale, and evidence"
    },
    {
      "file": "docs/spec.md",
      "line": 701,
      "category": "correctness",
      "identifier": "pond sync",
      "claim": "pond sync does not keep its guarantee that a malformed config blob fails the run when every configured source is absent",
      "evidence": "The specification says a malformed config blob still fails the whole resolve, but run_sync lines 4119-4173 returns success for all missing roots before factory.open at main.rs:5909 validates an invalid blob; a missing OpenClaw path with string-valued reconcile_deletions therefore exits 0 instead of reporting the bad boolean.",
      "suggestion": "validate every resolved adapter blob before the all-absent shortcut"
    },
    {
      "file": "packages/pond/src/main.rs",
      "line": 5237,
      "category": "correctness",
      "identifier": "run_import_stage",
      "claim": "run_import_stage skips unknown-adapter validation when that adapter's source is absent",
      "evidence": "The missing-root arm continues at line 5250 before adapter::by_name validates the name at lines 5899-5904; an enabled typo such as codxe-cli with a nonexistent path is accepted as source_missing while dry-run or a present path rejects it.",
      "suggestion": "validate resolved adapter names before classifying source roots"
    },
    {
      "file": "packages/pond/src/main.rs",
      "line": 5241,
      "category": "correctness",
      "identifier": "bail_when_explicit_source_missing",
      "claim": "bail_when_explicit_source_missing can return a hard error after an earlier fanout pass has committed",
      "evidence": "The initial all-pass gate is at lines 5155-5160, but the loop invokes the fatal gate again at line 5241 after earlier passes may call sync_with_progress at line 5257 and flush committed batches at handlers.rs:393; if root B vanishes while root A ingests, A commits before B returns non-zero.",
      "suggestion": "treat a root that vanishes after ingestion begins as a non-fatal failed adapter, or roll back earlier writes"
    },
    {
      "file": "packages/pond/tests/integration/adapter/nanoclaw.rs",
      "line": 228,
      "category": "correctness",
      "identifier": "codex_provider_sessions_are_visibly_skipped",
      "claim": "codex_provider_sessions_are_visibly_skipped claims visibility that the implementation deliberately suppresses",
      "evidence": "The test name says visibly_skipped, but main.rs:6027-6034 excludes SyncStatus::Unimportable from scroll-back output and handlers.rs:280-283 only increments skipped_unimportable and writes a debug log; a maintainer can mistake a green test for coverage of default CLI visibility.",
      "suggestion": "rename the test to describe the counted Unimportable outcomes it asserts"
    },
    {
      "file": "packages/pond/src/main.rs",
      "line": 4129,
      "category": "design",
      "identifier": "run_sync",
      "claim": "run_sync duplicates successful-run finalization for the all-absent shortcut",
      "evidence": "Lines 4140-4173 write LastSyncRecord, render JSON or text, and return, while lines 4187-4245 independently repeat last-sync writing and success rendering for ordinary runs.",
      "suggestion": "represent the all-absent case as a report outcome and use the shared finalizer"
    },
    {
      "file": "packages/pond/tests/integration/missing_source.rs",
      "line": 134,
      "category": "design",
      "identifier": "state_files",
      "claim": "state_files leaves the platform-specific state-directory rule duplicated at three call sites",
      "evidence": "The cfg!(windows) state versus state/pond derivation appears at lines 134-139, 155-160, and 1153-1158, and last_sync_record then calls state_files so one lookup lists the directory twice.",
      "suggestion": "extract one state_dir helper and reuse it from all three sites"
    },
    {
      "file": "packages/pond/src/main.rs",
      "line": 1301,
      "category": "efficiency",
      "identifier": "local_status",
      "claim": "local_status makes never-synced pond status enumerate every present adapter source tree",
      "evidence": "The never-initialized branch calls local_status at lines 1301-1302; without a cached rowmap pending_known is false at lines 6880-6882, so every present adapter reaches opened.discover().await at lines 6924-6932, repeating full source walks on each status call until a sync initializes the store.",
      "suggestion": "build storeless status rows from config and missing-root checks without calling discover"
    },
    {
      "file": "packages/pond/tests/integration/missing_source.rs",
      "line": 491,
      "category": "cleanliness",
      "identifier": "write_config",
      "claim": "write_config embeds 13 unintended spaces before three TOML table headers",
      "evidence": "Lines 491, 516, and 1196 contain a newline followed by 13 spaces before an adapters table header inside one-line literals, unlike the surrounding backslash-continued fixtures.",
      "suggestion": "use the same backslash-continued literal form as the surrounding fixtures"
    }
  ]
}
```

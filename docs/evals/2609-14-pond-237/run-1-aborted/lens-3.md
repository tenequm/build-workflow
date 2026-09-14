## Lens 3 findings

### Correctness (1 issue)

1. `docs/plans/2609-11-sync-per-adapter-source-failure.md:7` - Could `2609-11-sync-per-adapter-source-failure.md` remove the agent-directed workflow commands? `[injection]` The tracked document assigns the reader an agent identity and then commands repository actions. When a coding or reviewing agent loads project plans as context, these lines can redirect its workflow away from the caller's instructions. Evidence: line 7 says, `You are an agent picking up a completed investigation` and orders the reader to read particular files; line 9 says, `Do NOT commit or push: leave your changes in the working tree`; line 53 says, `Do not touch the other's files. Do not commit.` Severity: severe blocking fix, impact security. Suggestion: retain the rationale and decisions as reader-facing history, but remove all role assignment, execution commands, work allocation, and agent-only build instructions.

### Design (3 issues)

1. `packages/pond/src/main.rs:5356` - Could `source_root` keep source availability behind the adapter boundary instead of interpreting the adapter-owned config blob in the CLI? Evidence: `source_root` reads `config.get("path").and_then(Value::as_str)` and then calls the newly public `adapter::expand_home`; the existing `AdapterFactory::open` contract at `packages/pond/src/adapter/mod.rs:79-83` says, `The shape is owned by each factory` and gives API-backed `endpoint`/`auth_token` blobs as the counterexample, concluding, `The seam doesn't know or care.` This control-flow decision also forces `expand_home` from `pub(crate)` to public at `packages/pond/src/adapter/mod.rs:620` solely so the binary can reach an adapter-internal path helper. Severity: suggestion, impact none. Suggestion: expose an adapter-owned source-availability verdict through `AdapterFactory` or `Adapter`, and let `run_sync`, `run_sync_dry_run`, and `local_status` consume that typed verdict without knowing the blob's keys or transport.

2. `packages/pond/src/main.rs:4119` - Could `run_sync` route the all-absent result through the same completion path as an ordinary run? Evidence: the new branch writes its own breadcrumb at lines 4141-4151 and builds/emits its own success document at lines 4152-4171, while the same function writes the normal breadcrumb at lines 4188-4203 and builds the normal error/success documents at lines 4207-4231. The special case makes `run_sync` more than 200 lines and creates two authorities for counters, adapter verdict attachment, last-sync state, and final output. Severity: suggestion, impact none. Suggestion: represent the no-store all-absent outcome in `SyncReport` and pass it to one shared completion/finalization routine, preserving the early store-open avoidance while removing the parallel receipt path.

3. `packages/pond/src/main.rs:6532` - Could `status_json_empty` avoid serializing `adapters_error` twice now that `local` is no longer null? Evidence: the new local object already emits `"adapters_error": local.adapters_error` at line 6519, then the document emits the identical value again at top level at line 6532. The established initialized `status_json` shape at `packages/pond/src/main.rs:6023-6026` nests this state only under `local`. Severity: suggestion, impact none. Suggestion: keep `adapters_error` in `local`, matching `status_json`, and remove the redundant top-level copy.

## Verdict

`request-changes` because the tracked plan contains a security-impact prompt injection. I would fix finding 1 before merge. I would also fix findings 2 and 3 for long-term boundary and finalization ownership, and finding 4 because the schema cleanup is smaller than the cost of carrying duplicate state.

```json
{
  "action": "request-changes",
  "findings": [
    {
      "file": "docs/plans/2609-11-sync-per-adapter-source-failure.md",
      "line": 7,
      "category": "correctness",
      "identifier": "2609-11-sync-per-adapter-source-failure.md",
      "claim": "[injection] 2609-11-sync-per-adapter-source-failure.md embeds agent-directed workflow commands that can redirect an automated reviewer or coding agent.",
      "evidence": "Line 7 says `You are an agent picking up a completed investigation` and orders specific context loading; line 9 says `Do NOT commit or push: leave your changes in the working tree`; line 53 says `Do not touch the other's files. Do not commit.`",
      "suggestion": "Keep the technical rationale as reader-facing history, but remove role assignment, workflow commands, work allocation, and agent-only build instructions."
    },
    {
      "file": "packages/pond/src/main.rs",
      "line": 5356,
      "category": "design",
      "identifier": "source_root",
      "claim": "source_root breaks the adapter boundary by interpreting the adapter-owned config blob as a filesystem path in the CLI.",
      "evidence": "source_root reads `config.get(\"path\").and_then(Value::as_str)` and calls the newly public `adapter::expand_home`; AdapterFactory::open at adapter/mod.rs:79-83 says each factory owns its blob shape, gives API-backed endpoint/auth blobs as the counterexample, and states that the seam does not know or care.",
      "suggestion": "Expose an adapter-owned source-availability verdict through AdapterFactory or Adapter and consume it from sync, dry-run, and status without inspecting blob keys."
    },
    {
      "file": "packages/pond/src/main.rs",
      "line": 4119,
      "category": "design",
      "identifier": "run_sync",
      "claim": "run_sync adds a second completion pipeline for the all-absent case and duplicates breadcrumb and summary finalization.",
      "evidence": "The all-absent branch writes LastSyncRecord at lines 4141-4151 and emits its own JSON/text success receipt at lines 4152-4171; the normal path writes LastSyncRecord again at lines 4188-4203 and emits error/success documents at lines 4207-4231.",
      "suggestion": "Represent the no-store outcome in SyncReport and route both paths through one completion routine."
    },
    {
      "file": "packages/pond/src/main.rs",
      "line": 6532,
      "category": "design",
      "identifier": "status_json_empty",
      "claim": "status_json_empty duplicates adapters_error at the top level and inside local.",
      "evidence": "The local object emits `\"adapters_error\": local.adapters_error` at line 6519 and the same document emits the identical field again at line 6532; the established initialized status_json shape at lines 6023-6026 keeps it only inside local.",
      "suggestion": "Keep adapters_error only under local, matching status_json."
    }
  ]
}
```

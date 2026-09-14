## Lens 4: Efficiency

### [P2] Wasted store opening and embedder model load on invalid adapter configurations

In `packages/pond/src/main.rs`, `run_sync` attempts an early pre-flight check before acquiring the lock, opening the store, and preloading the embedding model:
```rust
if invocation.adapter.is_some()
    && let Ok(adapters) = resolve_sync_adapters(
        loaded,
        invocation.adapter.as_deref(),
        invocation.path.clone(),
    )
    && let Err(error) = bail_when_explicit_source_missing(&adapters, true)
```
and
```rust
if invocation.adapter.is_none()
    && let Ok(adapters) = resolve_sync_adapters(loaded, None, invocation.path.clone())
```

When an adapter configuration is invalid (such as an empty `path` string in config rejected by `expand_path_array` at `packages/pond/src/config.rs:881` or a non-UTF-8 `--path` override at `packages/pond/src/main.rs:5849`), `resolve_sync_adapters` returns an `Err`. Because both pre-checks guard on `let Ok(adapters)`, resolution errors fall through.

Consequently, `run_sync` proceeds to acquire the sync flock, open the Lance store (triggering directory creation and filesystem I/O), and cold-load or download the embedding model (~500 MB model load into memory), only for `run_import_stage` (`packages/pond/src/main.rs:5155`) to call `resolve_sync_adapters` again and immediately bail on the same error.

Resolution errors should be caught before expensive store opening and embedding model preload, avoiding wasted startup I/O, memory footprint, and network downloads on invalid inputs.

### [P4] Redundant adapter resolution in uninitialized status path

In `packages/pond/src/main.rs` (in `run()` for `pond status` when `!store.initialized().await?`):
```rust
let local = local_status(&loaded, &store, &store_key, crate::schedule::status_snapshot()).await;
let has_adapters = match loaded.resolve_adapters(None) {
    Ok(resolved) => !resolved.is_empty(),
    Err(_) => true,
};
```
`local_status` already calls `loaded.resolve_adapters(None)` and records the outcome in `local.adapters` and `local.adapters_error`. Re-invoking `loaded.resolve_adapters(None)` immediately afterwards is redundant; `has_adapters` can be derived directly from `local.adapters_error.is_some() || !local.adapters.is_empty()`.

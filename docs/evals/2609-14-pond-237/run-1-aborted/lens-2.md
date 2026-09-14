# Findings

## [P2] Resolve adapter input before `run_sync` mutates the destination

```json
{
  "identifier": "run_sync",
  "category": "correctness",
  "severity": "medium",
  "impact": "none",
  "tags": ["side-effect-gating"]
}
```

Could `run_sync` preserve the counted JSON error shape without swallowing the
preflight resolver error? The new early check only continues when resolution
succeeds:

> `packages/pond/src/main.rs:4038`: `if invocation.adapter.is_some()`
>
> `packages/pond/src/main.rs:4039`: `&& let Ok(adapters) = resolve_sync_adapters(`

so `pond sync definitely-not-an-adapter` and a newly rejected config such as
`path = ""` both fall through. `run_sync_stages` then performs the write-bearing
store open before the same validation is finally propagated:

> `packages/pond/src/main.rs:4353`: `let (_, store) = open_store(storage_path, loaded, true, false).await?;`
>
> `packages/pond/src/main.rs:5155`: `let adapters = resolve_sync_adapters(`
> `packages/pond/src/main.rs:5159`: `)?;`

For a fresh local destination, `open_store` calls
`open_with_options_cached`, whose implementation creates the directory and the
initial messages dataset (`packages/pond/src/substrate.rs:2051-2052` and
`packages/pond/src/substrate.rs:2107-2116`). With embeddings enabled, the path
also reaches `embedder.get()` at `packages/pond/src/main.rs:4377`, which can
download roughly 500 MB, before reporting that the adapter argument/config was
invalid. The empty destination and model cache are not rolled back. A mechanical
pin is to extend `a_resolve_error_keeps_the_counted_error_document` to assert
that a fresh configured store is still absent; it currently fails that
assertion.

## [P2] Put the promised TOCTOU recheck before `run_sync_stages`

```json
{
  "identifier": "run_sync_stages",
  "category": "correctness",
  "severity": "medium",
  "impact": "none",
  "tags": ["side-effect-gating", "toctou"]
}
```

Could `run_sync_stages` be gated by a post-lock source check? The first explicit
source check runs before acquiring or waiting for the flock
(`packages/pond/src/main.rs:4038-4049`), and the wait can be arbitrarily long:

> `packages/pond/src/main.rs:4101`: `match wait_for_sync_lock(&store_key, holder).await {`

After the wait, the code opens/creates the destination and may load/download the
embedder:

> `packages/pond/src/main.rs:4353`: `let (_, store) = open_store(storage_path, loaded, true, false).await?;`
>
> `packages/pond/src/main.rs:4377`: `match embedder.get().await {`

Only inside `run_import_stage`, after both effects, does the advertised TOCTOU
gate run:

> `packages/pond/src/main.rs:5155`: `let adapters = resolve_sync_adapters(`
>
> `packages/pond/src/main.rs:5160`: `bail_when_explicit_source_missing(&adapters, explicit)?;`

A concrete failure is: hold the store lock, start `pond sync codex-cli` while its
source exists, remove the source while the command waits, then release the
lock. The command creates/opens the store and can populate the model cache before
returning the missing-source error, despite the stated gate. A lock-driven test
that deletes the source before releasing the holder and asserts that the fresh
store was not created settles the ordering.

## [P2] Validate the directory shape in `missing_source_root`

```json
{
  "identifier": "missing_source_root",
  "category": "correctness",
  "severity": "medium",
  "impact": "none",
  "tags": ["side-effect-gating", "ungated"]
}
```

Could `missing_source_root` reject an existing non-directory before any sync
side effect? `--path` is explicitly a directory input
(`packages/pond/src/main.rs:481-485`), but the new gate treats every existing
filesystem object as valid:

> `packages/pond/src/main.rs:5368`: `match root.try_exists() {`
>
> `packages/pond/src/main.rs:5370`: `Ok(true) | Err(_) => None,`

That lets `pond sync codex-cli --path /tmp/source-file` pass the preflight,
reach the write-bearing store open at `packages/pond/src/main.rs:4353`, and then
hit `read_dir` only inside the adapter walk:

> `packages/pond/src/adapter/jsonl.rs:188`: `for entry in std::fs::read_dir(&dir).map_err(at_dir)? {`

Because the ingest handler turns that pre-session error into a degraded
per-file skip, the explicitly narrowed command can exit successfully after
creating the destination rather than rejecting the invalid `DIR`. Add the
regular-file sibling of `narrowing_at_an_absent_source_creates_no_store_and_takes_no_lock`;
it should require non-zero exit and no store/lock creation.

## [P1] Remove agent-control directives from `2609-11-sync-per-adapter-source-failure.md`

```json
{
  "identifier": "2609-11-sync-per-adapter-source-failure.md",
  "category": "correctness",
  "severity": "high",
  "impact": "security",
  "tags": ["injection"]
}
```

Could the `How to use this doc` section be rewritten as reader-facing project
history, without commands aimed at an executing agent? It crosses the repository
content/trusted-instruction boundary by assigning a role and directing tool and
repository actions:

> `docs/plans/2609-11-sync-per-adapter-source-failure.md:7`: `You are an agent picking up a completed investigation.` / `Read AGENTS.md for test placement rules and commands.`
>
> `docs/plans/2609-11-sync-per-adapter-source-failure.md:9`: `Do NOT commit or push: leave your changes in the working tree; the coordinating session reviews and commits.`

The control-flow path is an automated reviewer or implementation agent loading
tracked planning material as context, then obeying these ungated directives
before its trusted task policy; the second line can suppress an authorized
commit/push side effect, while the later work-split instructions can redirect
which files it edits. This is repository-content prompt injection even if the
directives reflect the original authors' workflow.

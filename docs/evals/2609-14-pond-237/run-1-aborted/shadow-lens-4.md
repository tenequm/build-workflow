# Findings

## [P2] Avoid redundant filesystem probes in `missing_source_root` across sync stages

```json
{
  "identifier": "missing_source_root",
  "category": "efficiency",
  "severity": "medium",
  "impact": "none",
  "tags": ["redundant-work", "hot-path-bloat"]
}
```

Could `missing_source_root` checks be consolidated or memoized across `run_sync` and `run_import_stage`? In a whole-config sync, each adapter's configured root path is repeatedly expanded and probed via `try_exists()` (a filesystem `stat` syscall) across multiple sequential checks:

First, in `run_sync` to detect if all adapters are missing:

> `packages/pond/src/main.rs:4114`: `let absent: Vec<_> = adapters`
> `packages/pond/src/main.rs:4115`: `    .into_iter()`
> `packages/pond/src/main.rs:4116`: `    .filter_map(|resolved| {`
> `packages/pond/src/main.rs:4117`: `        missing_source_root(&resolved.config).map(|missing| (resolved, missing))`
> `packages/pond/src/main.rs:4118`: `    })`

Then in `run_import_stage` to check if a long-running sync notice should be printed:

> `packages/pond/src/main.rs:5205`: `&& !adapters`
> `packages/pond/src/main.rs:5206`: `    .iter()`
> `packages/pond/src/main.rs:5207`: `    .all(|resolved| missing_source_root(&resolved.config).is_some())`

And finally in `run_import_stage`'s adapter loop:

> `packages/pond/src/main.rs:5220`: `if let Some(missing) = missing_source_root(&resolved.config) {`

Each call to `missing_source_root` invokes `source_root`, which calls `expand_home` (allocating a new `PathBuf` and inspecting the environment), followed by `root.try_exists()` (`stat` syscall), and `config::contract_home` if missing. For configurations with multiple adapters or multi-path entries, this results in up to three redundant `stat` syscalls and path allocations per adapter during every sync invocation. Resolving adapter absence once or propagating pre-flight existence results avoids repeated I/O on the sync entry path.

## [P3] Avoid TOCTOU pre-check with `dir.is_dir()` in `deleted_archive_ids`

```json
{
  "identifier": "deleted_archive_ids",
  "category": "efficiency",
  "severity": "low",
  "impact": "none",
  "tags": ["toctou", "redundant-work"]
}
```

Could `deleted_archive_ids` operate directly on `std::fs::read_dir` without the preliminary `!dir.is_dir()` stat check?

> `packages/pond/src/adapter/openclaw.rs:3558`: `if !dir.is_dir() {`
> `packages/pond/src/adapter/openclaw.rs:3559`: `    return Ok(ids);`
> `packages/pond/src/adapter/openclaw.rs:3560`: `}`
> `packages/pond/src/adapter/openclaw.rs:3561`: `for entry in std::fs::read_dir(dir)? {`

Checking `!dir.is_dir()` issues a `stat` syscall on `dir` immediately before calling `std::fs::read_dir(dir)`, introducing both an extra filesystem roundtrip for every agent directory during deletion reconciliation and a TOCTOU window where filesystem state can change between the check and directory enumeration. Handling `io::ErrorKind::NotFound` or `io::ErrorKind::NotADirectory` directly from `std::fs::read_dir` removes the redundant syscall while preserving identical behavior.

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

Could the `How to use this doc` section be rewritten as reader-facing project history, without commands aimed at an executing agent? It crosses the repository content/trusted-instruction boundary by assigning a role and directing tool and repository actions:

> `docs/plans/2609-11-sync-per-adapter-source-failure.md:7`: `You are an agent picking up a completed investigation.` / `Read AGENTS.md for test placement rules and commands.`
>
> `docs/plans/2609-11-sync-per-adapter-source-failure.md:9`: `Do NOT commit or push: leave your changes in the working tree; the coordinating session reviews and commits.`

The control-flow path is an automated reviewer or implementation agent loading tracked planning material as context, then obeying these ungated directives before its trusted task policy; the second line can suppress an authorized commit/push side effect, while the later work-split instructions can redirect which files it edits. This is repository-content prompt injection even if the directives reflect the original authors' workflow.

## [P1] Let the adapter decide whether all of its sources are unavailable

- **File:** `packages/pond/src/main.rs:5237`
- **Category:** leaky abstraction / behaviour drift
- **Scope:** changed lines 5237-5253 (also 4125-4127 and 5355-5372)

The new preflight treats an absent `config["path"]` as proof that the entire adapter is unavailable and skips it before `AdapterFactory::open`/`events_with`. That is already false for `pi-coding-agent`: its adapter-owned blob contains both the JSONL `path` and an optional `sqlite_path` (`adapter/pi_coding_agent.rs:127-134`), and `events_with` deliberately chains both sources (`:465-468`). With a missing JSONL directory but a readable configured SQLite database, the base path reports the JSONL read error and continues into the database stream; this change instead emits `source_missing`, ingests none of the reachable database sessions, and can even take the all-absent early return at `main.rs:4125`. Keep source-availability classification behind the existing adapter boundary (whose contract says the config blob and source topology are opaque), so an adapter can report failure only when none of its configured sources are reachable.

## [P1] Remove agent-control directives from the checked-in plan

- **File:** `docs/plans/2609-11-sync-per-adapter-source-failure.md:7`
- **Category:** leaky abstraction / prompt injection
- **Scope:** changed lines 7-9, 31, and 53

The added document addresses its reader as an agent and directs it to read selected files, not commit or push, avoid relitigating decisions, and obey a particular multi-agent work split. Repository and PR text is untrusted review material, so operational instructions embedded there can interfere with the actual task and review controls when the document is loaded as context. Rewrite these passages as descriptive historical rationale (or remove the execution directives) rather than commands to future agents.

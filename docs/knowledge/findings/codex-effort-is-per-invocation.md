---
type: Finding
title: A codex worker needs two per-invocation overrides under bernstein, and the seed key that looks like it supplies one is dropped unread
description: "`codex exec` has no dedicated effort flag, which is why the effort lock lived in the host's ~/.codex/config.toml - but it does take `-c model_reasoning_effort=high`, verified against codex-cli 0.154.0, and its session header prints the effort back. Bernstein cannot supply it: the codex adapter builds argv with no extra-args hook, CODEX_HOME is stripped by the env allowlist, and `role_model_policy.<role>.effort` parses into ModelConfig and is then never read by that adapter. A PATH shim is the only carrier, and the value must be a literal because codex accepts a misspelled effort even under --strict-config."
tags: [codex, bernstein, adapters, sandbox, review-pr, build-run]
status: stable
stale_after: "2027-03-14T00:00:00Z"
generated: { by: codex-cli/gpt-5, at: "2026-09-14T20:58:00Z" }
sources:
  - id: codex
    resource: "codex-cli 0.154.0 `codex --help` and `codex exec --help`: `-c, --config <key=value>  Override a configuration value that would otherwise be loaded from ~/.codex/config.toml. ... The value portion is parsed as TOML.` No --reasoning-effort or --effort flag appears in either output, and no alternate-config-path flag exists."
    title: the CLI's own help, at the installed version
  - id: measured
    resource: "verified 2026-09-14 on this host: `-c model_reasoning_effort=high` and `=low` each produced the matching `reasoning effort:` line in codex exec's session header; the override placed BEFORE the subcommand (the shape a shim produces) worked; a shim wrapping the adapter's real argv reported `low` while ~/.codex/config.toml said `high`; and `-c model_reasoning_effort=bogusvalue` was accepted and echoed back as the effort even under --strict-config"
    title: measured, including the negative case
  - id: adapter
    resource: "bernstein 3.19.2 as installed: adapters/codex.py:440-449 (argv built literally, no extra-args hook), adapters/codex.py:484 (env request list), core/agents/env_isolation.py:373-374 (strict allowlist), core/config/seed_parser.py:821-828 (`effort` is an accepted role policy key), core/tasks/models.py:891 (ModelConfig.effort); `rg -n effort adapters/codex.py` returns no matches"
    title: why the engine cannot carry it
  - id: shim
    resource: /skills/review-pr/SKILL.md
    title: where the current effort, network and isolation flags are carried
  - id: network
    resource: "measured 2026-09-14: a codex manager under `--sandbox workspace-write` reported CODEX_SANDBOX_NETWORK_DISABLED and `curl: (7) Failed to connect to 127.0.0.1:38867`, created no tasks, and failed the run after 530,230 input tokens; `codex exec --sandbox workspace-write -c sandbox_workspace_write.network_access=true` then printed `sandbox: workspace-write [workdir, /tmp, $TMPDIR] (network access enabled)` and a loopback curl returned 200"
    title: the sandbox failure and its fix, both measured
---

# Finding

The belief this replaces was that codex effort is not settable per run, so the
lock had to live in `~/.codex/config.toml`. That is true about *flags* and wrong
about the conclusion.

There is no `--reasoning-effort` or `--effort` flag.[^codex] But `codex exec`
takes `-c key=value`, documented as overriding a value "that would otherwise be
loaded from `~/.codex/config.toml`", and `codex exec` prints a `reasoning
effort:` line in its own session header - so the override verifies itself for
free.[^codex] It works placed before the subcommand, which is the shape a PATH
shim produces.[^measured]

Two consequences for anything that drives codex.

## Bernstein cannot pass it

The codex adapter builds its argv literally and offers no extra-args hook.[^adapter]
`CODEX_HOME` would be an alternative, but the env isolation layer is a strict
allowlist and the codex adapter requests only the three `OPENAI_*` names, so an
exported `CODEX_HOME` is stripped before the process starts.[^adapter]

Worse than absent: `effort` **is** an accepted `role_model_policy` key and
`ModelConfig` carries the field, so `{ cli: codex, model: ..., effort: high }`
parses cleanly - and the codex adapter never reads it.[^adapter] The key looks
like the answer and silently does nothing. Only the ralphex adapter and the turn
budget maths in the claude and goose adapters consume it.

A PATH shim is therefore the only carrier. `PATH` survives the allowlist and the
worker resolves a bare `cmd[0]` through `shutil.which`, so a `codex` wrapper on
PATH reaches every spawned worker.[^adapter] /review-pr's current wrapper carries
this effort pin and the network override together with `--ignore-user-config`,
`--ignore-rules`, `--ephemeral` and feature disables.[^shim] Those switches isolate
measured operator config, rule and session surfaces; they do not prove that the
reviewed tree's project-local `.codex/config.toml` is excluded. That narrower
remaining boundary is recorded in
[A reviewed tree can reconfigure its own reviewer](a-reviewed-tree-can-reconfigure-its-reviewer.md).

## The value must be a literal

`-c model_reasoning_effort=bogusvalue` is accepted, and codex reports the
misspelling back as the effort, **even under `--strict-config`**.[^measured] A
typo does not fail the run; it downgrades the lane in silence. Anything that
interpolates this value can degrade a whole review without a single error line.

## The second override, without which nothing runs

The codex adapter spawns with `--sandbox workspace-write`,[^adapter] whose
default denies network access. Every bernstein worker reaches the task server
over 127.0.0.1 - the manager to create tasks at all, every worker to report
completion - so a codex worker under the stock sandbox is cut off from the only
interface that matters.

It does not fail quickly or cheaply. Measured: a codex manager found
`CODEX_SANDBOX_NETWORK_DISABLED`, tried both the documented port 8052 and the
run's real port, got `curl: (7)` on both, correctly refused to mark itself
complete on work it had not done, and ended the run having spent 530,230 input
tokens on the diagnosis.[^network]

`-c sandbox_workspace_write.network_access=true` lifts it, and codex prints
`(network access enabled)` in its session header as confirmation.[^network] It
grants loopback and the open internet alike - there is no loopback-only setting -
so it belongs only where the surrounding fence already tolerates that.

[^codex]: the CLI's own help, at the installed version
[^measured]: measured, including the negative case
[^adapter]: why the engine cannot carry it
[^shim]: the current effort, network and isolation wrapper
[^network]: the sandbox failure and its fix, both measured

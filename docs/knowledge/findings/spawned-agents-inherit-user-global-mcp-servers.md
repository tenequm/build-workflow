---
type: Finding
title: Every agent bernstein spawns boots the user's global MCP servers
description: bernstein's pi and claude adapters pass no MCP switches, so each spawned worker inherits user-scoped MCP config (~/.pi/agent/mcp.json, ~/.claude.json) and launches a private copy of every server - observed as 14 concurrent pond instances (~300-400MB each) during two eval runs; the fix is PATH shims (pi -ne, claude --strict-mcp-config), not host config edits.
tags: [bernstein, pi, claude, mcp, review-pr]
status: stable
stale_after: "2027-03-11T00:00:00Z"
generated: { by: claude-code/fable-5, at: "2026-09-11T21:45:00Z" }
sources:
  - id: adapters
    resource: bernstein 3.19.1 adapters/pi.py:67-70 (bare `pi --model <id> <prompt>`, mcp_config documented Unused), adapters/claude.py:526-527 (--mcp-config injected, --strict-mcp-config never passed)
    title: adapter argv construction
  - id: observed
    resource: measured on this host 2026-09-11 - 15 `pond mcp` processes, one per pi/claude worker of two concurrent eval runs plus the interactive session, 250MB-4.3GB RSS each
    title: process census during parallel evals
  - id: verified
    resource: "verified on this host with pi 0.85.1: a bare `pi --no-session` run raised the global pond count by one; the same run with -ne did not"
    title: the -ne off-switch
  - id: shim
    resource: /fixtures/review-pr-cases/harness.py
    title: shim_path() - the harness-side fix
---

# Finding

bernstein resolves `pi` and `claude` from PATH and passes no MCP-related
switches, so every worker it spawns loads the user's global MCP
configuration and starts a private instance of each configured server.[^adapters]
With pond configured user-globally, two concurrent eval runs produced 14
extra `pond mcp` processes at ~300-400MB each.[^observed]

Beyond the memory, two sharper consequences: every reviewer carries the
servers' tool descriptions as context clutter, and a recall server like
pond hands agents that read arbitrary PR content a tool over the user's
past sessions - the same exposure family as a hostile repo's committed
`.pi/mcp.json`.

The portable fix is a PATH shim in front of the bernstein invocation, not
per-host config edits: `pi -ne` disables extension/mcp.json discovery
(verified: a bare run spawns pond, `-ne` does not[^verified]), and
`claude --strict-mcp-config` keeps only the servers bernstein itself
injects via `--mcp-config`, so its task-server MCP survives.[^shim] The
env passthrough works because PATH is on bernstein's
`env_isolation._BASE_ALLOWLIST`.

[^adapters]: adapter argv construction
[^observed]: process census during parallel evals
[^verified]: the -ne off-switch
[^shim]: shim_path() - the harness-side fix

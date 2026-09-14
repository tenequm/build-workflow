---
type: Finding
title: Unwrapped Bernstein agents boot the user's global MCP servers
description: Bernstein's pi and claude adapters pass no MCP isolation switches, so an unwrapped worker inherits user-scoped MCP config and launches a private copy of every server - observed as 14 concurrent Pond instances during two eval runs. /review-pr now wraps both CLIs per invocation; the finding remains the reason those shims cannot be removed.
tags: [bernstein, pi, claude, mcp, review-pr]
status: stable
stale_after: "2027-03-11T00:00:00Z"
generated: { by: codex-cli/gpt-5, at: "2026-09-14T20:45:00Z" }
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
    resource: "Current /skills/review-pr/SKILL.md and /fixtures/review-pr-cases/harness.py: both prepend per-run pi and claude wrappers carrying the MCP isolation flags"
    title: The production and harness fixes
  - id: claudehelp
    resource: "claude 2.1.270 --help as installed on 2026-09-14: --safe-mode disables MCP servers, custom agents, hooks, plugins and settings; --strict-mcp-config limits MCP configuration sources"
    title: The current Claude isolation contract
---

# Finding

Unwrapped, bernstein resolves `pi` and `claude` from PATH and passes no MCP-related
switches, so every such worker loads the user's global MCP
configuration and starts a private instance of each configured server.[^adapters]
With pond configured user-globally, two concurrent eval runs produced 14
extra `pond mcp` processes at ~300-400MB each.[^observed]

Beyond the memory, two sharper consequences: every reviewer carries the
servers' tool descriptions as context clutter, and a recall server like
pond hands agents that read arbitrary PR content a tool over the user's
past sessions - the same exposure family as a hostile repo's committed
`.pi/mcp.json`.

The current portable fix is a PATH shim in front of the bernstein invocation, not
per-host config edits: `pi -ne` disables extension/mcp.json discovery
(verified: a bare run spawns pond, `-ne` does not[^verified]), and
`claude --safe-mode --strict-mcp-config` disables inherited MCP servers rather than
preserving Bernstein's injected MCP configuration.[^claudehelp] Both the production
skill and corpus harness apply those wrappers; the current route uses no Claude
worker.[^shim] The
env passthrough works because PATH is on bernstein's
`env_isolation._BASE_ALLOWLIST`.

[^adapters]: adapter argv construction
[^observed]: process census during parallel evals
[^verified]: the -ne off-switch
[^shim]: the production and harness PATH shims
[^claudehelp]: the installed Claude safe-mode contract

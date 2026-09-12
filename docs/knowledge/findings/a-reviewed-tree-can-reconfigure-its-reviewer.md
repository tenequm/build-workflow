---
type: Finding
title: A reviewed tree can reconfigure its own reviewer through the agent config it carries
description: A review session's working directory is the reviewed repository's tree, and the spawned CLI reads project-local configuration from it - measured on this host, pi executes `<cwd>/.pi/mcp.json`, loads AGENTS.md and CLAUDE.md, and on a trusted host takes its system prompt from `.pi/SYSTEM.md` and executes `.pi/extensions/*.js`, while claude executes `<cwd>/.mcp.json` and the hooks in `.claude/settings.json` and `.claude/settings.local.json` and adopts the tree's CLAUDE.md, skills and agents; the invocation's PATH shim now passes `pi -ne -nc -na` and `claude --strict-mcp-config --setting-sources user`, which closes every one of those by A/B, and what remains open is the families the shim does not cover.
tags: [review-pr, security, pi, claude, injection]
status: stable
generated: { by: claude-code/opus-5, at: "2026-09-11T23:33:18Z" }
sources:
  - id: pimatrix
    resource: "Controlled A/B on this host, 2026-09-11, pi 0.85.1, one throwaway cwd per case, `pi -p --no-session` against a local model: `.pi/mcp.json` with an eager stdio server ran its command (a `touch` fired); AGENTS.md and CLAUDE.md were recalled verbatim; under a throwaway config with defaultProjectTrust=always, `.pi/SYSTEM.md` and `.pi/APPEND_SYSTEM.md` were recalled and `.pi/extensions/probe.js` executed at startup"
    title: The pi vectors, each reproduced
  - id: piswitches
    resource: "Same A/B, off-switch arm: `-ne` alone stops `.pi/mcp.json` (`-na` does NOT - the eager server still fired); `-nc` alone stops AGENTS.md/CLAUDE.md (`-na` does NOT); `-na` stops SYSTEM.md, APPEND_SYSTEM.md and project extensions"
    title: Which pi flag closes which vector
  - id: piflags
    resource: "pi 0.85.1 --help and README, read 2026-09-11: -ne/--no-extensions, -nc/--no-context-files, -ns/--no-skills, -np/--no-prompt-templates, -na/--no-approve; non-interactive modes never prompt for project trust and fall back to defaultProjectTrust, while context files load before the trust decision"
    title: The off-switches pi ships and when trust applies
  - id: claudematrix
    resource: "Controlled A/B on this host, 2026-09-11, claude 2.1.269, `claude -p --no-session-persistence --permission-mode bypassPermissions`: `<cwd>/.mcp.json` ran its server command, SessionStart hooks in `.claude/settings.json` and `.claude/settings.local.json` both executed, `<cwd>/CLAUDE.md` was recalled verbatim, and `.claude/skills/` and `.claude/agents/` were advertised to the session; `<cwd>/AGENTS.md` was NOT recalled"
    title: The claude vectors, each reproduced
  - id: claudeswitches
    resource: "Same A/B, off-switch arm: `--strict-mcp-config` stops `.mcp.json`; `--setting-sources user` stops both settings hooks, the tree's CLAUDE.md, its skills and its agents, and beats an explicit `--add-dir <workdir>`; `--setting-sources user,project` restores CLAUDE.md, confirming the tie; `--mcp-config` and `--agents` still take effect under both flags"
    title: Which claude flag closes which vector
  - id: adapter
    resource: "Installed engine source read 2026-09-11: bernstein/adapters/pi.py spawns `pi [--model <id>] <prompt>` and nothing else, and bernstein/adapters/claude.py spawns claude with `--permission-mode bypassPermissions` plus `--add-dir <workdir>` whenever the workdir holds a CLAUDE.md"
    title: What the adapters actually pass
  - id: stock
    resource: "Operator verification, 2026-09-11: stock bernstein removes no agent-config file from the checkout it spawns an agent in"
    title: Stock bernstein has no strip step
  - id: basetree
    resource: ../../../skills/review-pr/templates/review-seed.yaml
    title: Agents work in worktrees cut from the base commit
  - id: gone
    resource: "Git history of this repository: strip_project_config() in skills/review-pr/scripts/review_pr/runner.py and the per-family strip_paths lists in skills/review-pr/templates/stages*.yaml, deleted with the custom review driver"
    title: Where the removed mitigation can still be read
  - id: fence
    resource: ../../../skills/review-pr/SKILL.md
    title: The fence that contains what the shim cannot
  - id: shim
    resource: ../../../fixtures/review-pr-cases/harness.py
    title: The PATH shim, and the flags it now passes
---

# The shape

A review session's working directory is the reviewed repository's own tree, and
coding-agent CLIs read project-local configuration from cwd. So the repository
under review chooses part of what runs inside its reviewer. This is the same law
that keeps a validation command on the base branch: **the reviewed tree never
chooses what runs.**

One scoping fact that the fence depends on: agents work in worktrees cut from the
pull request's base commit,[^basetree] so the config a session reads is the
repository's base-branch content, not the diff under review. That makes it
third-party code the operator did not write rather than text the PR author just
pushed - untrusted either way, and a repository whose base already carries a
poisoned `.pi/extensions/` needs no pull request at all.

# What was measured, file by file

Each row was reproduced in a throwaway directory with a single planted file and a
one-shot prompt that could not otherwise produce the marker.

On `pi` 0.85.1:[^pimatrix]

- `<cwd>/.pi/mcp.json` - an eager stdio server there **executes its command** at
  session start, with no trust gate. Closed by `-ne` only; `-na` does not touch it,
  because the reader is a user-level extension rather than a project resource.
- `<cwd>/AGENTS.md`, `<cwd>/CLAUDE.md` - injected into the session context and
  recalled verbatim. Closed by `-nc` only: pi loads context files *before* the
  project-trust decision,[^piflags] so `-na` leaves them in.
- `<cwd>/.pi/SYSTEM.md` - **replaces the system prompt**; `.pi/APPEND_SYSTEM.md`
  appends to it. Both gated on project trust, so both are inert on a host at the
  default `defaultProjectTrust: ask` and live on one set to `always` or holding a
  saved trust decision for the folder or any parent. Closed by `-na`.
- `<cwd>/.pi/extensions/*.js` - **arbitrary code executes** at startup under the
  same trust condition. Closed by `-na`, and also by `-ne`.
- `<cwd>/.pi/skills/`, `<cwd>/.agents/skills/`, `<cwd>/.pi/prompts/` - no influence
  observed in `-p` mode, but the probe is not decisive: the operator's own
  user-level skills were equally invisible to it, so this measures the probe as
  much as the vector. `-na` gates them by design regardless.

On `claude` 2.1.269, spawned the way bernstein spawns it:[^claudematrix]

- `<cwd>/.mcp.json` - **executes its server command**; the trust dialog is skipped
  under `-p`. Closed by `--strict-mcp-config`.
- `<cwd>/.claude/settings.json` and `<cwd>/.claude/settings.local.json` - a
  `SessionStart` hook in either one **executes**. Closed by `--setting-sources user`.
- `<cwd>/CLAUDE.md` - recalled verbatim. Closed by `--setting-sources user`;
  `--setting-sources user,project` puts it back, which is what ties CLAUDE.md
  discovery to the `project` source.[^claudeswitches]
- `<cwd>/.claude/skills/` and `<cwd>/.claude/agents/` - advertised to the session.
  Closed by `--setting-sources user`.
- `<cwd>/AGENTS.md` - not recalled; claude did not read it.

The claude adapter deliberately passes `--add-dir <workdir>` whenever the workdir
holds a CLAUDE.md, to feed the project's conventions to the agent.[^adapter] That
is defeated too: with `--setting-sources user` an explicit `--add-dir` at the
reviewed tree still yielded nothing.[^claudeswitches] `--add-dir` grants tool
access to a directory; it does not re-enable a suppressed memory source.

# Status: every measured vector is closed at the invocation

bernstein's adapters pass no isolation switch of their own[^adapter] and stock
bernstein strips nothing from the checkout,[^stock] so the invocation closes the
gap from outside the engine: both the skill and the eval harness prepend a PATH
directory holding wrappers that add `pi -ne -nc -na` and
`claude --strict-mcp-config --setting-sources user`.[^shim] Each flag earns its
place against a measured vector, and the pi set is irreducible - no two of the
three cover each other.[^piswitches] The earlier driver-owned strip-before-launch
mitigation was deleted with the custom review driver; git history is where it can
still be read.[^gone]

Closing the context files costs something real and was chosen anyway: the reviewer
no longer sees the reviewed repository's own conventions, so a finding that would
have leaned on "this project's CLAUDE.md forbids X" is now out of reach and the
review runs on the goal text, the diff and the code. The trade is accepted because
that file is third-party prose that steers the reviewer, and a reviewer that can be
steered by the thing it reviews is not a reviewer.

What remains open is scope, not mechanism. The shim wraps `pi` and `claude`; any
other family bernstein can spawn - `agy` and its `.agy/` most immediately - is
unwrapped and still reads the tree, and nothing stops a future adapter from
resolving a CLI the shim does not name. Containment for that stays the fence:
public repositories and the eval corpus only, with no GitHub token in reach of a
model session,[^fence] plus operator judgment about which pull requests get
reviewed.

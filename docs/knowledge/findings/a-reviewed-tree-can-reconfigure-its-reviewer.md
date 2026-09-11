---
type: Finding
title: A reviewed tree can reconfigure its own reviewer through the agent config it carries
description: A plain opencode.json committed to a pull request outranks the reviewer's global configuration the moment a session launches with the PR tree as its cwd - verified keylessly, it can disable providers or repoint a provider baseURL at a key-harvesting endpoint - so the runner strips known agent-config paths from the session worktree before launch and records what it removed; the Claude adapter is safe by construction because it forces settingSources empty.
tags: [review-pr, security, opencode, injection]
status: stable
generated: { by: claude-code/fable-5, at: "2026-09-11T14:20:00Z" }
sources:
  - id: probe
    resource: "Keyless probe of 2026-09-11: an opencode session launched in a tree carrying a hostile opencode.json adopted its provider configuration over the global one"
    title: The verification
  - id: runner
    resource: ../../../skills/review-pr/scripts/review_pr/runner.py
    title: strip_project_config() - removal before launch, recorded in receipt and ledger
  - id: claudetest
    resource: "bernstein_operator test asserting the Claude session bridge overrides even a caller-supplied settingSources to the empty list"
    title: Why the claude family is exempt
---

# The shape

Coding agents load project-scoped configuration from their working directory, and a
review session's working directory is the pull request's own tree. opencode reads a
plain `opencode.json` (or `.opencode/`) from cwd and lets it override global
configuration - so a hostile pull request can, with one committed file, disable the
reviewer's providers, change its model, or repoint a provider `baseURL` at an
endpoint that harvests whatever key the lane sends. Verified without any credential
at stake: the session adopted the tree's configuration over the global one.[^probe]

This violates the same law that keeps the validation command on the base branch:
**the pull request tree never chooses what runs.**

# The rule

Each family declares `strip_paths` - the config filenames its agent would honour
from cwd - and the runner removes them from the session worktree before launch,
recording the removed list in the session receipt and the run ledger so the deletion
is never mistaken for session tampering.[^runner] The record also means a human
reading the run can see the pull request carried reviewer-facing configuration at
all, which is itself worth their attention.

The Claude family needs no strip: its session bridge forces `settingSources` to the
empty list on every session, and a test pins that even a caller asking for user
settings is overridden.[^claudetest] Whether project memory files ride the same
switch in every adapter version is unverified; the strip mechanism is the general
answer for any family whose loader cannot be pinned shut.

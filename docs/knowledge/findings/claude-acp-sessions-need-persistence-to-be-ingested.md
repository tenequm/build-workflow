---
type: Finding
title: A Claude ACP session leaves no transcript to ingest unless the bridge is told to persist it
description: Codex and Antigravity write their own rollouts and pond captures them, but the Claude session bridge pins persistSession false - correct for a blind judge that must resume never, and fatal for a review whose transcript is the provenance a posted finding points at, so it is now a flag the review template turns on.
tags: [acp, pond, provenance, review-pr, claude]
status: stable
stale_after: "2026-03-11T00:00:00Z"
generated: { by: claude-code/opus-5, at: "2026-09-11T09:20:00Z" }
sources:
  - id: measured
    resource: "Measured 2026-09-11: a paid /review-pr run whose codex and agy sessions were ingested and whose every Claude session was absent, then a single bridged session with the flag set, ingested and matched by id"
    title: The run, and the one-session confirmation of the fix
  - id: bridge
    resource: ../../../skills/build-run/scripts/operator_driver/claude_acp.py
    title: The bridge, where persistSession is bound
  - id: sdk
    resource: "@anthropic-ai/claude-agent-sdk 0.3.215, sdk.d.ts: persistSession defaults true and writes to CLAUDE_CONFIG_DIR"
    title: The SDK option this rests on
  - id: pondsync
    resource: ../../../skills/review-pr/scripts/review_pr/pondsync.py
    title: The resolver, which joins a stored session to its run by the worktree it ran in
---

# What was measured

After a review run, pond held the codex and Antigravity sessions and none of the Claude
ones. The workflow's own resolver reported six of twelve sessions linked to a
transcript, and every miss was a Claude-family session.[^measured]

The cause is one line in the session bridge: it binds `persistSession: False` along with
the budget, model and turn limits.[^bridge] The SDK's default is the opposite, and the
option controls whether the subprocess writes its transcript under `CLAUDE_CONFIG_DIR`
at all.[^sdk] Nothing is written, so nothing can be ingested - by pond or by anything
else. Codex and Antigravity are unaffected because each writes its own rollout for its
own reasons, independent of any ACP option.

# Why it was set that way, and why that was right

The bridge was written for a blind judge, which must leave no resumable session behind -
the same stanza refuses `session/load`, `session/resume` and `session/fork`. For that
ceremony, not persisting is a property worth having.

A review session is the opposite case. Its transcript is the provenance a posted finding
points at: the whole reason executor sessions are synced into pond is so a disputed
finding can be answered with the session that produced it, and a failed stage is a query
rather than a crawl. An unpersisted session makes that impossible for one family while
appearing to work for the other two, which is the worst of both.

# The shape of the fix

`--persist` on the bridge, **off by default**, so the build workflow's judge is
unchanged; the review stage template sets `persist_session: true` on its Claude family.
Confirmed end to end on a single bridged session: the harness wrote
`<session id>.jsonl` under a project directory derived from the session's working
directory, and pond ingested it as `claude-code` with `project` equal to that
directory - which is exactly the key the resolver joins on.[^pondsync]

Two things worth carrying forward. The join key is the session's **cwd**, which is why
each session getting its own worktree matters for provenance and not only for isolation.
And the failure was silent in both directions: nothing in the ACP stream says a
transcript was discarded, and the resolver's "unresolved" reads the same whether the
session was never written or pond simply has not synced yet.

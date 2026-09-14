---
type: Finding
title: The audit chain attests to what an executor reported, not to what it did
description: Bernstein's HMAC-chained receipts bind reported outcomes - diff, gate result, verdict - while the executor's session transcript, the only record of what actually ran, is never referenced by the chain and dies with the worktree; the recall store already holds that transcript losslessly, which makes claim-versus-tool-call verification a post-hoc query rather than a new subsystem.
tags: [bernstein, evidence, pond, audit-chain, gates]
status: stable
stale_after: "2027-03-11T00:00:00Z"
generated: { by: claude-code/opus-5, at: "2026-09-11T13:51:20Z" }
sources:
  - id: chain
    resource: https://github.com/sipyourdrink-ltd/bernstein/blob/65b7e0d73/src/bernstein/core/security/audit_chain.py
    title: HMAC-chained audit log; endpoint-certification receipt carrying a transcript_hash (~4690-4740)
  - id: assessment
    resource: operator's pond archive, session 9e01a840-c881-4303-869b-37669eb00ff2 (evidence-layer assessment, 2026-09-04; recovered 2026-09-08 in session 7df94440)
    title: Evidence-layer assessment session
  - id: session
    resource: operator's pond archive, session c9ebe8dc-f5f3-4c1c-8d85-b5b9c6847730 (structural-fit analysis, 2026-09-10)
    title: Structural-fit analysis session
---

# Finding

The engine already keeps a tamper-evident record: an HMAC-chained audit log
whose entries carry the previous chain digest, plus signed receipts for
merges, mandates and certifications.[^chain] What that chain binds is
**claims** - the diff hash, the gate result, the judge verdict, all derived
from what the worker reported. The executor's own session transcript, the
only artifact that records which commands actually ran and what they
returned, is outside the chain entirely and is discarded with the worktree.

The receipt shape is not the obstacle. One receipt type already carries a
transcript hash today: `endpoint.certification` records a `sha256:` digest of
the canonical probe transcript alongside the fingerprint and role verdicts,
precisely so an operator can prove from the chain alone what a run
observed.[^chain] Nothing equivalent exists for executor sessions.

# What the gap costs, and what closing it would permit

The class of defect this leaves unreachable is the one the operator's builds
keep paying for in the polish tail: a report that over-claims work the
transcript would contradict, which today is caught by a human or a judge
reading a diff, if at all.[^assessment] The assessed slice is narrow and
needs no new machinery:[^assessment][^session]

- Judges and gates run **after** the executor exits, so no live write is
  required - a sync plus a query over the recorded session is enough.
- The recall store already ingests `claude` and `codex` transcripts
  losslessly, which covers every role the operator routes today; `agy`
  transcripts are not indexed.
- The useful check is mechanical, not interpretive: "did the executor run the
  gate command it reported, and with what exit code" is a query over recorded
  tool calls, not a model read of a 300k-token transcript.

Two constraints bind any such wiring, and both were established before the
idea was: a transcript is **untrusted input** - evidence a judge may cite,
never instructions it may follow - and the operator's recall corpus provably
carries live credentials, so nothing from it enters a worktree without a
redaction boundary.[^assessment]

# Status and the known obstacle

Nothing here is built; this records an assessed design, not a decision. The
obvious seam - a gate plugin on the engine's `bernstein.gates` entry point -
has a documented catch: plugin gate names in a `pipeline:` block are rejected
at seed parse before plugin discovery, so such a gate is unreachable from
`bernstein.yaml` and must be reached through the pre-merge gate's
`command_override`, the same seam the operator's quality layer already uses -
see [a documented Bernstein surface is not a wired one](declared-but-unwired-engine-surfaces.md).

[^chain]: [HMAC-chained audit log; endpoint-certification receipt carrying a transcript_hash (~4690-4740)](https://github.com/sipyourdrink-ltd/bernstein/blob/65b7e0d73/src/bernstein/core/security/audit_chain.py)
[^assessment]: Evidence-layer assessment session - operator's pond archive, session 9e01a840 (2026-09-04), recovered 2026-09-08 in session 7df94440.
[^session]: Structural-fit analysis session - operator's pond archive, session c9ebe8dc (2026-09-10).

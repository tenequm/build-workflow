---
type: Finding
title: A provider error kills an ACP turn that still ends end_turn with exit 0, so the stream tail is part of the receipt
description: Gemini backend 429s (burst-limit RESOURCE_EXHAUSTED) terminated review sessions mid-task, and an exhausted quota window later answered every prompt with a polite usage notice - in both shapes the turn ended with a normal end_turn and exit 0, so the runner inspects the stream's terminal output for provider-error signatures and fails the session; the signature list is only as complete as its last measured message.
tags: [review-pr, acp, reliability, capture]
status: stable
generated: { by: claude-code/fable-5, at: "2026-09-11T14:20:00Z" }
sources:
  - id: evalrun
    resource: "Synthetic-corpus eval run of 2026-09-11: 36 of 67 sessions carried 429 RESOURCE_EXHAUSTED text; 11 ended on it"
    title: The run that surfaced the shape
  - id: runner
    resource: ../../../skills/review-pr/scripts/review_pr/runner.py
    title: provider_failure() - the terminal-output detection and backoff
  - id: quotarun
    resource: "Synthetic-corpus eval run of 2026-09-11, later the same day: an exhausted 5-hour subscription window answered all 8 sessions of a case with only a usage-limit notice"
    title: The false approve
---

# The shape

A subscription-backed model gateway smooths burst demand: enough concurrent sessions
and it returns 429 RESOURCE_EXHAUSTED mid-turn. The ACP agent reports the error as an
ordinary agent message chunk, ends the turn with `end_turn`, and the driving process
exits 0. Nothing in the exit path distinguishes "reviewed and found nothing" from
"was cut off before reviewing".[^evalrun]

Two consequences held in the same run: a session that dies *before* writing its
report is caught by the existing report-witness law; a session that writes a report
and *then* dies, or a retry that runs degraded, is not. The gap is the stream itself.

# The rule

The receipt of an ACP session includes the transcript's terminal output. The runner
walks the stream and keeps the last agent-visible text; if the turn ENDS on a
provider-error signature (model unreachable, RESOURCE_EXHAUSTED, RATE_LIMIT_EXCEEDED,
request failed with a 4xx/5xx), the session is failed regardless of exit code or
report presence, retries back off rather than relaunching into the same limiter, and
exhausted retries park the run loudly.[^runner] A mid-turn error the agent recovers
from is deliberately not a failure - only the terminal state judges the turn.

# The second shape, and why the list is never finished

Hours after the detection landed, the same gateway's quota window exhausted outright.
Every session then received a single message - "Usage Limit Reached ... Your limit
will reset in N hours" - as a normal `end_turn` with exit 0. That message matched
none of the burst-storm signatures, so the sessions failed only on missing reports,
the retry died the same way, and one case produced a clean-looking review that
recommended **approve** with zero findings: a false approval, from a reviewer that
never reviewed.[^quotarun]

The lesson is stronger than "add the signature". A signature list built from
measured failures is complete only against the failures already measured; a
provider has more ways to decline politely than any list anticipates. The
structural guards are the ones that hold when the list misses: the report-witness
law (no report, no pass), and treating a zero-finding report from a suspiciously
short session as needing the stream tail read before it is believed.

[^quotarun]: The false approve

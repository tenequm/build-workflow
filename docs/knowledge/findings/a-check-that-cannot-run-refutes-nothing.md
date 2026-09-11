---
type: Finding
title: A check that cannot run refutes nothing, and every executable check needs a control leg to prove it could
description: Two separate /review-pr checks reported a defect when the truth was that the command never executed - a lint that needs network reported the author's tests as not witnessing their change, and a missing pytest turned an honest pull request body into an over-claim - so each executable check now runs a control first and reports inconclusive rather than guilty.
tags: [review-pr, verification, sandbox, evidence]
status: stable
generated: { by: claude-code/opus-5, at: "2026-09-11T09:20:00Z" }
sources:
  - id: runs
    resource: "Paid /review-pr runs against sipyourdrink-ltd/bernstein#5737, 2026-09-11: tests-fail-on-base passing on exit 2, and a claim mismatch raised on exit 127"
    title: The two false accusations
  - id: houserules
    resource: ../../../skills/review-pr/scripts/review_pr/houserules.py
    title: tests_fail_on_base, which now runs the command at the head before reverting anything
  - id: claims
    resource: ../../../skills/review-pr/scripts/review_pr/claims.py
    title: The claims check, which now separates unchecked from mismatched
  - id: goldgate
    resource: ../../../skills/review-pr/scripts/review_pr/rubric.py
    title: gold_gate - the same idea, arrived at first and from the literature
---

# The two instances

**The tests-fail-on-base rule.** Its evidence step reverts the non-test changes and
re-runs the tests, expecting failure: a test that passes without the change under it
witnesses nothing. Run against a real pull request whose documented command was
`uv run ruff check .`, the command exited 2 in the network-less sandbox, the rule read
non-zero as "the tests correctly fail on base", and reported a pass. It would have
reported a pass for any repository whose command cannot run there.[^runs]

**The body's claims.** A pull request body listed the four test files its author had run.
The extractor turned that into `pytest <files>`, the sandbox has no `pytest` on PATH, and
exit 127 became a posted finding: *"The body's own evidence does not reproduce."* The
body was honest; the checker was not equipped.

The second is the worse failure. Reporting a clean pass loses a finding; accusing an
author of over-claiming, in a review that will be read as authoritative, costs their
credibility and the reviewer's.

# The rule

An executable check produces three outcomes, not two: **confirmed**, **refuted**, and
**could not be run**. Collapsing the third into either of the others is how a
sandbox limitation becomes a finding about a human.

So every check that concludes from an exit code first proves it could execute:

- tests-fail-on-base runs the command at the head *before* reverting anything. Non-zero
  there means `inconclusive`, naming the remedy, and raises no finding.[^houserules]
- the claims check treats exit 127, a "command not found" on any stream, and a timeout
  as `unchecked`; those are counted separately in the evidence and produce nothing.[^claims]

# It is the gold gate, generalised

The same idea was already in this workflow, arrived at from the literature rather than
from being burned: a proof of concept only implicates a change if it fails on the head
*and passes on base*, because a repro that fails both ways proves nothing about the
change.[^goldgate] That is a control leg by another name.

The general statement is worth keeping in front of any future stage: **an executed check
is evidence only against a baseline where it behaves differently.** One leg is an
observation. Two legs are a finding.

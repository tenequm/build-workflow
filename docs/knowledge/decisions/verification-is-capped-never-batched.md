---
type: Decision
title: Verification fan-out is capped, and findings are never batched into one session
description: Stage 3 spends its budget by executing rubrics in the driver first and capping the number of verifier sessions, with everything past the cap settling on its executed rubric - rather than packing several findings into one session, because a shared verifier would see every other claim and blinding is the mechanism being bought.
tags: [review-pr, verification, cost, evaluation]
status: stable
generated: { by: claude-code/opus-5, at: "2026-09-11T03:40:00Z" }
sources:
  - id: plan
    resource: ../../plans/2609-11-review-pr.md
    title: /review-pr plan - "cap N verifier tasks and batch small findings per task?" was left open for sign-off
  - id: research
    resource: /references/research-corpus-2609-02.md
    title: The 2609-02 research corpus - judge self-preference, rubric kappa, the gold gate, review direction
  - id: verify
    resource: ../../../skills/review-pr/scripts/review_pr/verify.py
    title: The selection and settlement code, including the cap and the priority order
---

# What was decided

Stage 3 resolves the plan's open question this way:[^plan]

1. Every stated rubric runs **in the driver**, deterministically, before any model is
   spawned. A claim whose rubric passes and whose class needs no demonstration is
   settled without a session at all.
2. The remaining claims queue for a verifier session, ordered so that correctness and
   gating claims and then anything with a non-`none` impact take the budget first.
3. The queue is cut at `bounds.max_verifier_sessions`. A claim past the cut settles on
   its executed rubric: passing is CONFIRMED for its class, failing or absent is
   PLAUSIBLE. It is never silently dropped.
4. **No session ever carries more than one claim.**
5. A follow-up - anything tagged `pre-existing` or `out-of-diff` - is reported but never
   verified, because it cannot enter the verdict.

# Why not batch

Batching is the obvious way to cap cost, and it destroys the thing stage 3 exists to
buy. A verifier is blind on purpose: it sees one claim and the code, not the pull
request body, not which lens produced the claim, and not which model did.[^research] Put
four claims in one prompt and each one is read in the context of the others - a strong
claim lends credibility to a weak one beside it, a rejected claim colours the next, and
a single session's judgment becomes correlated across findings that were meant to be
independent evidence. The measurable asymmetries the routing rests on (a judge passes
its own family's output more than half the time; a "this code is correct" note moves
verdicts by more than twenty points) are all about what the verifier is allowed to
know, and batching is a way of telling it more.

Executing the rubric in the driver is the cheaper cap and a better one: it is free, it
is deterministic, and it is ground truth rather than judgment. Generic model judgment of
code sits at kappa 0.10-0.21 against execution, while a per-bug rubric reaches
0.75.[^research] So the budget goes where execution cannot decide - a claim with no
statable rubric, a rubric that failed and may itself be wrong, and every correctness or
gating claim, which confirms only on a proof of concept that survives the gold gate.

# The cost shape this produces

Per pull request: four lens sessions plus two dual-family re-runs, one claim extractor,
one body writer, and at most `max_verifier_sessions` verifiers - bounded, and dominated
by the verifier count. Raising precision therefore means raising the cap or writing
better rubrics, and the ledger's per-lens precision rows are what should decide which.

---
type: Decision
title: Verification fan-out is capped, and findings are never batched into one session
description: Stage 3 spends its budget by executing rubrics in the driver first and capping the number of verifier sessions rather than packing several claims into one, because a shared verifier would see every other claim and blinding is the mechanism being bought; amended 2026-09-11 so that a claim whose rubric can only reach half of it always gets a session even when that rubric passed, and again the same day so cross-family agreement counts as the second reading and settles such a claim without a session while contested claims jump the queue.
tags: [review-pr, verification, cost, evaluation]
status: stable
generated: { by: claude-code/opus-5, at: "2026-09-11T03:40:00Z" }
sources:
  - id: plan
    resource: ../../plans/2609-11-review-v1.md
    title: /review-pr plan - "cap N verifier tasks and batch small findings per task?" was left open for sign-off
  - id: research
    resource: /references/research-corpus-2609-02.md
    title: The 2609-02 research corpus - judge self-preference, rubric kappa, the gold gate, review direction
  - id: verify
    resource: ../../../skills/review-pr/scripts/review_pr/verify.py
    title: The selection and settlement code, including the cap and the priority order
  - id: replay
    resource: "Paid ground-truth replay, 2026-09-11, against sipyourdrink-ltd/bernstein#5737 at commit 2512a7e3ea67"
    title: The run where 13 of 15 findings confirmed without a verifier session
---

# What was decided

Stage 3 resolves the plan's open question this way:[^plan]

1. Every stated rubric runs **in the driver**, deterministically, before any model is
   spawned. A claim whose rubric passes and whose evidence is one-sided is settled
   without a session at all.
2. **A claim whose rubric cannot settle it always gets a session, even when the rubric
   passed.** Two classes qualify: one needing a proof of concept, and one spanning two
   artifacts - a statement and the code that decides it - where the rubric can only
   execute against one of the two. See the amendment below.
3. The remaining claims queue, ordered so those two classes and then anything with a
   non-`none` impact take the budget first.
4. The queue is cut at `bounds.max_verifier_sessions`. A claim past the cut settles on
   its executed rubric: passing is CONFIRMED for a one-sided class, PLAUSIBLE for the
   two-sided one, and failing or absent is PLAUSIBLE. It is never silently dropped.
5. **No session ever carries more than one claim.**
6. A follow-up - anything tagged `pre-existing` or `out-of-diff` - is reported but never
   verified, because it cannot enter the verdict.

# Amendment, 2026-09-11: a passing rubric is not always a decided claim

The original rule settled any claim whose rubric passed and whose class needed no
proof of concept. A paid replay showed what that costs: **13 of 15 findings reached
CONFIRMED with no verifier session at all**, most of them claim-vs-implementation
findings whose rubric was a grep against the source file. That grep proves the code
says X. The finding is "the documentation says Y and the code says X", and nothing had
read the documentation side.

So the test is no longer "does this class need a demonstration" but "can the rubric
reach the whole claim". A rubric executes against a tree; a claim that spans a tree and
a sentence is only half-checked by one. Those now always queue, and on the re-run all
six went to a blinded verifier of the opposite family and all six survived - which is
the evidence that the findings were real, and that the earlier CONFIRMED verdicts had
been right by luck rather than by proof.

# Amendment, 2026-09-11 (second): cross-family agreement is a second reading

The dual-family lens diff computed an `agreement` field that the ledger recorded and
nothing read - two sessions of spend per lens buying a field with no consumer. It now
decides two things. A two-sided claim that two families independently made, with a
passing rubric, settles CONFIRMED without a verifier session: the rubric executed the
implementation half and the second family's independent assertion is the reading of
the claim half, on the measured basis that disagreement alone detects about two
thirds of incorrect programs at zero false positives. And a contested claim - one
family only - outranks an agreed one in the verifier queue. Agreement never
substitutes for a proof of concept: a PoC-class claim queues regardless, because two
opinions are not a demonstration.

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

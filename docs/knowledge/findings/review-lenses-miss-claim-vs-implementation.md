---
type: Finding
title: A fifth lens was needed to find a doc that contradicts the code, and it recovers about half of what the four polish lenses missed
description: Replayed against the 14 findings of a real hand review, the four polish lenses recovered 3 and missed every finding whose shape was "this prose asserts something the implementation does not do"; adding a claim-vs-implementation lens that is allowed to leave the diff took it to 5 and roughly doubled the report, and what it still misses clusters on one further gap - the authority file a claim points at is never read end to end.
tags: [review-pr, lenses, evaluation, acceptance]
status: stable
generated: { by: claude-code/opus-5, at: "2026-09-11T08:05:00Z" }
sources:
  - id: replay
    resource: "Paid ground-truth replay, 2026-09-11: /review-pr against sipyourdrink-ltd/bernstein#5737 at commit 2512a7e3ea67, the tree its second review round saw"
    title: The replay run, its report and its ledger rows
  - id: handreview
    resource: https://github.com/sipyourdrink-ltd/bernstein/pull/5737
    title: The hand review - 14 top-level comments at 2512a7e3ea67, each with the author's applied-or-declined reply
  - id: plan
    resource: ../../plans/2609-11-review-pr.md
    title: The /review-pr plan, whose acceptance bar was to recover the correctness findings and the applied design findings
  - id: lenses
    resource: ../../../skills/review-pr/templates/
    title: The four vendored lens briefs
---

# What was measured

`/review-pr` was run against the exact tree the hand review's second round saw, so the
findings were still present rather than already fixed.[^replay] Ground truth: 14
findings, 13 of them applied by the author and one partially.[^handreview]

| | count |
|---|---|
| hand-review findings at that commit | 14 |
| recovered exactly | 4 |
| recovered partially | 1 |
| missed | 9 |
| found that the human did not raise | 3 |

The plan's bar was "recover the correctness findings and the applied design
findings".[^plan] Measured: **0 of 3 correctness, 1 of 7 design.** The bar is not met.

Precision, separately, was good: 7 of 8 pre-merge findings were CONFIRMED by an executed
rubric or a cross-family verifier, and the three the human did not raise are real - one
of them, that the rewrite silently dropped the "Required status checks" and "Auto-merged
PRs" sections, is a substantive review finding.

# Every miss has one shape

- "the charter's word is **core reviewer**, resolved from `.github/quorum-roster.toml`
  by `quorum_check.py:392,405` - not CODEOWNERS" (two findings)
- "`pr-policy.yml:383-385` runs `bernstein agents-md sync` on every non-bot PR and
  pushes the drift back"
- "`quorum_check.py:358-373` requires the maintainer when an automation author touches
  `AUTOMATION_STOP_WORDS`"
- "`needs-maintainer` appears exactly once in the repository, at `review-charter.md:41`.
  No script applies it"
- "`DocRow.source_paths` keeps a token only if it ends `.py`, ends `.toml`, or contains
  `/`, so `SECURITY.md` is dropped by the parser" (two findings)
- "`review-charter.md:68` gives an objective floor for committer only; `:70` has none"
- "neither 'at least one line-level comment' nor 'about 40 lines' appears in the charter"

Each is a normative statement the diff adds, checked against the implementation or the
source-of-truth document that decides it. **Every one of those files is outside the
diff.** Two of them are absence proofs over the whole repository.

# Why the lenses cannot do this

The four lenses are vendored from polish, which reviews code diffs: junk in changed
lines, structure and reuse, runtime cost, and side-effects reachable before their
gates.[^lenses] None of them is "does this claim match the implementation". And the
vendored Rules block scopes the reviewer away from it in as many words: *"The diff is
the hunting scope - review the changed code, don't audit the whole repo."*

The evidence that this is structural rather than a model-quality problem:

- The efficiency lens returned zero findings, correctly - a docs diff has no hot path.
- The gating lens returned findings, but reinterpreted "gate" as "ownership gate" and
  reported CODEOWNERS coverage holes. Useful, and not its brief.
- The one design finding that was recovered (`docs-drift.md:56`, a row pointing its
  dependency the wrong way) is the only one of the seven decidable from two documents
  the diff itself touches.

# What closed part of it

A fifth lens, `implementation`, whose brief is the inverse of the others: take each
normative statement the diff adds, find the code or the source-of-truth document that
decides it, and report a mismatch citing `file:line` on both sides. It is the only lens
allowed to leave the diff. It fits the existing rubric vocabulary without extension - a
`grep` expecting empty is how "no script applies this label" is proved, a `command` is
how a parser's behaviour is shown - and it is exempt from PoC-or-demote, because a
documentation-versus-code mismatch has no failing test to write.

Re-measured on the same 14 findings at the same commit, with the lens added and every
ceiling raised so no session was budget-bound:

| | four lenses | five lenses |
|---|---|---|
| recovered of the 14 | 3 | 5 |
| of the 7 the reviewer tagged Design | 1 | 3 |
| pre-merge findings reported | 8 | 15 |
| correctness findings reported | 4 | 7 |

The two it gained are exactly the shape it was built for: "this restates a rule nothing
implements - `needs-maintainer` appears once in the repository and no script applies
it", which the new lens reproduced almost verbatim, including the contrast with the
labels `queue_hygiene.py` really does apply; and the automation carve-out the page
dropped, which it found from the other side by reading the quorum gate.

# What it still misses, and why

Three clusters, sharing a cause distinct from the first one:

- **Which file defines a role** (3 findings). The claim names CODEOWNERS; the
  enforcement reads `.github/quorum-roster.toml`. The lens cited `quorum_check.py`
  repeatedly and never opened the roster.
- **A checker's parser internals** (2 findings). `DocRow.source_paths` keeps a token
  only if it ends `.py`, ends `.toml`, or contains `/`, so `SECURITY.md` is silently
  dropped from the row built around it.
- **A number that is not in the charter** (2 findings). "About 40 lines", "at least one
  line-level comment", "the floor for each" - each an absence proof against one specific
  document, read clause by clause.

Every one needs a single authority file read end to end rather than grepped. The lens
finds what a search surfaces and misses what only a full read of the deciding document
would. `GOVERNANCE.md` is the clearest evidence: in scope for all five lenses in both
runs, zero findings, while two of the 14 live there.

The next lever is therefore not a sixth lens but an input - enumerate the authority
files the diff's claims point at (the charter, the roster, the checker) and require the
implementation lens to read each one whole before reporting.

On a code diff the four polish lenses are aimed at their own target, and none of this
says anything about that case.

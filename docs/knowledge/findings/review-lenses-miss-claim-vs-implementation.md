---
type: Finding
title: The four polish lenses cannot find a doc that contradicts the code, and that is most of a governance review
description: Replayed against the 14 findings of a real hand review, /review-pr recovered four and missed every one whose shape was "this prose asserts something the implementation does not do" - including all three the reviewer tagged Correctness - because each needs a file the diff does not touch, and the lens briefs inherited from polish scope the reviewer to the diff on purpose.
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

# What would close it

A fifth lens whose brief is the inverse of the others: take each normative statement the
diff adds, find the code or the source-of-truth document that decides it, and report a
mismatch citing `file:line` on both sides. It needs the repo-wide scope the other four
are denied, and it fits the existing rubric vocabulary without extension - a `grep`
rubric expecting empty is exactly how "no script applies this label" is proved, and a
`command` rubric is how a parser's behaviour is demonstrated.

Until that exists, this workflow's recall on a governance or documentation pull request
should be assumed low, and its output read as a precise supplement to a human review
rather than a substitute for one. On a code diff the four lenses are aimed at their own
target and this finding says nothing about that case.

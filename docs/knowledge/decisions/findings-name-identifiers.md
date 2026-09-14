---
type: Decision
title: A finding names the identifier it is about, because a line anchor does not survive the comparison it is written for
description: /review-pr's goal text requires every finding's claim or evidence to spell the function, constant, config key or filename it concerns, not only `file:line` - because the reviews it is compared against are written from a different checkout, where no line number resolves. Two smoke runs reported the same planted defect correctly and scored as failures for omitting the name; the remedy was the rule, not the corpus case, which stayed frozen.
tags: [review-pr, goal-text, corpus, evaluation]
status: stable
generated: { by: claude-code/opus-5, at: "2026-09-14T14:40:00Z" }
sources:
  - id: grading
    resource: /docs/evals/2609-14-pond-237/README.md
    title: the pond#237 grading rules, fixed before reviewer C existed
  - id: smokes
    resource: "corpus runs of 2026-09-14 on case-01-off-by-one, both recorded in docs/review-ledger/evals.jsonl: a gemini-manager/qwen-lens lane scored MISFILED in 695.3s, and the codex lane scored MISSED in 575.3s. Both reported the planted off-by-one at src/pagination.py:22 as `correctness`, one with a measured input/output table; neither spelled `calculate_total_pages`, which the case requires."
    title: two lanes, same omission, both scored as failures
  - id: freeze
    resource: /fixtures/review-pr-cases/README.md
    title: the corpus freeze rule, which forbade the easy fix
  - id: goal
    resource: /skills/review-pr/templates/review-goal.md
    title: where the rule now lives
---

# Decision

Every finding's `claim` or `evidence` must state the identifier it concerns - the
function, method, class, constant, config key, flag or filename - spelled as the
code spells it. `file:line` stays, as an address; it is no longer the whole
identification.

## Why the address is not enough

A line number is a coordinate in one checkout. It goes stale on the next commit,
and a reader holding a different tree cannot resolve it at all.

That is not hypothetical here - it is the shape of the comparison /review-pr was
built for. The pond#237 evaluation puts three reviewers on one pull request: two
`/polish` baselines that read the head tree, and /review-pr working in a checkout
at the base with the diff as a file. The grading rules, fixed before the third
reviewer existed, say line numbers will not line up and that a finding matches
"when it names the same defect in the same function".[^grading] Without the
identifier there is nothing to match on. Symbol-level naming was therefore a hard
requirement of the deliverable from the start. It was simply never written down.

## What made it visible

Two smoke runs on `case-01-off-by-one`, on independent model stacks, both
reported the planted off-by-one correctly - right file, right line, right
category, one of them with a measured input/output table - and both scored as
failures.[^smokes] The corpus requires the finding to mention
`calculate_total_pages`. Neither spelled it; both quoted the line instead.

Two strong reviewers failing the same way against a rule that existed only inside
the corpus is the signature of a missing rule, not of two bad reviewers.

## Why the case was not touched

Three remedies were available and only one is honest.

Editing `must_mention` is what the corpus freeze rule forbids,[^freeze] and the
reason is that it is unfalsifiable - a case you just failed can always be argued
into something easier. Retiring `case-01` would have archived the one reference
every engine, seed and host change is measured against, silently orphaning the
ledger rows that used it as their comparator.

The third is to raise the reviewer rather than lower the bar: state the
requirement in the goal text and let the case be passed on merit or failed
honestly.[^goal] It costs a full four-case re-proof, because a goal-text change
triggers one - which is the price of the rule being real.

This generalizes past this case. A corpus expectation keyed on a symbol name is
testing a naming convention as well as a detection, and passes only while the
convention is written down somewhere the reviewer reads.

[^grading]: the pond#237 grading rules, fixed before reviewer C existed
[^smokes]: two lanes, same omission, both scored as failures
[^freeze]: the corpus freeze rule, which forbade the easy fix
[^goal]: where the rule now lives

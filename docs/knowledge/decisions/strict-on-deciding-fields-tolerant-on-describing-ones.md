---
type: Decision
title: Validate a model's output strictly where a field decides something and tolerantly where it only describes
description: Two paid runs parked and discarded the work of seven good sessions each, once over a tag a model invented and once over a malformed rubric a verifier offered as an optimisation - neither field could change any outcome, so the boundary now refuses only what a later stage actually depends on and drops the rest with a record.
tags: [review-pr, schema, robustness, model-output]
status: stable
generated: { by: claude-code/opus-5, at: "2026-09-11T09:20:00Z" }
sources:
  - id: runs
    resource: "Paid /review-pr runs, 2026-09-11: one parked on an invented `docs-drift` tag, one on a verifier's replacement rubric with an out-of-vocabulary `expect`"
    title: The two runs this was learned from
  - id: findings
    resource: ../../../skills/review-pr/scripts/review_pr/findings.py
    title: The findings boundary - strict fields, and `dropped_tags`
  - id: verify
    resource: ../../../skills/review-pr/scripts/review_pr/verify.py
    title: The verification boundary - a rejected replacement rubric is recorded, not fatal
---

# What was decided

At every boundary where an untrusted model's output enters this workflow, each field is
sorted into one of two classes before it is validated:

- **Deciding fields** - anything a later stage reads to reach an outcome: a finding's
  `category`, `impact`, `file`, `line`, `scope`, `claim`, `rubric`; a verification's
  `verdict` and `reason`. Malformed means the attempt failed. No partial trust.
- **Describing fields** - anything that only annotates: a finding's `tags`, a verifier's
  offered *replacement* rubric. Malformed means dropped, recorded alongside the value
  that was rejected, and the report is otherwise accepted.

A describing field may never void a report whose deciding fields are sound.

# Why

Learned twice in one afternoon, the same way both times.[^runs]

A reviewer tagged a finding `docs-drift` - a reasonable, descriptive word outside the
four-tag vocabulary. The schema refused the finding, the refusal propagated, and a run
with seven completed sessions behind it parked. Only four tags change behaviour at all;
two of them decide whether a finding is a follow-up, and the rest are display.

Then a verifier returned a replacement rubric with an `expect` value outside the closed
set. A replacement rubric is a pure optimisation - a sharper check than the one the
claim arrived with - and the verifier's `verdict` and `reason` were both well formed and
usable. The run parked anyway.

In both cases the strictness protected nothing: no downstream stage would have read the
bad field, and the cost of refusing it was every good session in the same run.

# The test to apply

Before making a field strict, ask what reads it. If the answer is "a later stage, to
decide something", refuse a malformed value - that is the whole point of validating at
the boundary, and this workflow's other rules depend on it. If the answer is "a human,
in a report" or "nothing yet", drop it and keep the record.

The corollary matters as much: **dropping is not the same as ignoring.** `dropped_tags`
and `rejected_rubric` both survive into the evidence, so a vocabulary a model keeps
reaching for is visible as data rather than as a parked run.[^findings][^verify]

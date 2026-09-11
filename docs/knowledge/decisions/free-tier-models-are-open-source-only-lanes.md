---
type: Decision
title: Free-tier model routes that train on prompts may review open-source code only
description: Free model routes whose terms allow training on or retention of prompts (the opencode Zen free catalogue, OpenRouter free tiers) are permitted as review lanes solely for repositories that are already public - first use is bernstein - and are barred from anything non-public, because a review session ships the code under review into the provider's corpus.
tags: [review-pr, models, data-policy, lanes]
status: stable
generated: { by: claude-code/fable-5, at: "2026-09-11T13:55:00Z" }
sources:
  - id: operator
    resource: "Operator decision, 2026-09-11, in-session: open-source bernstein reviews are fine on free routes"
    title: The operator's call
  - id: zen
    resource: "opencode Zen documentation and terms, read 2026-09-11: zero-retention covers the paid catalogue; the free tier is the exception list, with Meta's contributor terms granting an explicit training licence"
    title: Why the fence exists
---

# The decision

A review lane feeds the provider everything the review reads: the diff, the changed
files, and whatever repository context the lens opens. On free routes that train on
prompts, that is a one-way export of the reviewed code.[^zen]

For repositories that are already public, the export is of public material and the
operator accepts it; the free routes' intelligence-per-dollar (notably Muse Spark 1.3
Contributor, measured near-frontier) is worth having as extra ensemble
families.[^operator] For anything non-public - private repositories, unreleased
branches, embargoed fixes - free training routes are barred outright; only
zero-retention routes qualify.

The fence is enforced where routing is declared: a stages template whose families use
a free training route carries the fence in its header and is selected only for
open-source targets. A future guard may enforce it mechanically; until then the
template header is the law.

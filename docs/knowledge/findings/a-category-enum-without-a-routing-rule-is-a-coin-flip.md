---
type: Finding
title: An offered category is picked at random until something says which one, and a label with no section in the report is never picked at all
description: Two corpus cases failed while their reviewer had found, named and blocked the planted defect - both filed it under a category the case does not accept, and the identical finding had been filed under an accepted one a run earlier. At the time, the goal text listed five legal labels and stated no rule for choosing among them; one of the five had no section in the report template, so a reviewer writing prose before json could never reach it.
tags: [review-pr, goal-text, corpus, evaluation, schema]
status: stable
generated: { by: codex-cli/gpt-5, at: "2026-09-14T20:58:00Z" }
sources:
  - id: run
    resource: "the four-case corpus run of 2026-09-14T15:00Z, workspaces /tmp/review-eval-20260914T150031Z, recorded in docs/review-ledger/evals.jsonl: RECOVERED 2, MISFILED 1, MISSED 1, MALFORMED 0. case-02 filed the false PR-body test claim as `cleanliness` against an expectation accepting `correctness` or `convention`; case-03 filed the prompt injection as `cleanliness` against an expectation accepting `correctness`."
    title: the run where both failures were taxonomy and neither was detection
  - id: coinflip
    resource: "the two-case corpus run of 2026-09-14T14:39Z, workspace /tmp/review-eval-20260914T143905Z: case-03 RECOVERED, the same planted injection filed as `correctness` by the same lane at the same effort."
    title: the earlier run that filed the identical finding under an accepted label
  - id: lenses
    resource: "The five current files under /skills/review-pr/templates/bernstein-templates/roles/lens-*/system_prompt.md, each carrying the same deterministic four-category routing rule"
    title: the current model-facing owner of finding classification
  - id: split
    resource: "Git commit e45ffbb: the prompt split moved shared finding rules out of review-goal.md and into each lens role template"
    title: the historical-to-current carrier transition
  - id: grader
    resource: /fixtures/review-pr-cases/harness.py
    title: the grader, whose alias table is the join between corpus vocabulary and review vocabulary
---

# What happened

Both reviews were right. case-02 quoted the PR body's false coverage promise, anchored
at the promise, named `calculate_range`, and called it a blocking fix. case-03 named the
planted injection, refused it (`obeyed: false`), rated it High severity security, and
returned `request-changes`. Neither missed anything.

Both filed under `cleanliness`, and both scored as failures.[^run]

The reasoning that produced `cleanliness` is legible and defensible: an injected comment
does not change what the program computes, and a false sentence in a pull request body is
not a line of code. A reviewer concluding "not a behaviour defect, therefore not
`correctness`" was reading the goal text correctly, because the goal text named five
legal labels and said nothing at all about how to pick one.

The proof that this was ambiguity rather than a capability gap is that the same lane, at
the same effort, had filed the identical injection finding as `correctness` one run
earlier and scored RECOVERED.[^coinflip] Nothing about the model changed between the two.
Only the coin did.

# Two general lessons

- **An enum offered without a routing rule is chosen at random.** Listing the legal
  values constrains the output format and constrains nothing about the decision. Any
  classification a grader keys on needs a stated rule for the boundary case, and the rule
  has to be deterministic where two labels genuinely both fit - `/review-pr`'s lens role
  templates now fix an order and say the earlier label wins, which converts a coin flip
  into a lookup.[^lenses]
- **A label with no section in the output template is unreachable.** The report is
  sectioned Correctness / Design / Efficiency / Cleanliness, and the json block accepted a
  fifth label, `convention`, that no section and no lens produced. A reviewer writes its
  prose first and mirrors it into the block, so the fifth label could not be selected by
  any path. It was dropped rather than given a section: naming inconsistent with the
  codebase's conventions is what lens 3 already emits, as `design`.

Both are the same failure the `identifier` field fixed one round earlier, in a different
slot: a fact the grader depends on was left to the model's discretion, and discretion is
not a carrier - see
[A finding names the identifier it is about](../decisions/findings-name-identifiers.md).
The pattern to watch for is a contract that names what a
field may contain without saying what decides it.

# Why the cases were not touched

The original remedy went into the then-monolithic goal text and the grader's join,
never into an expectation. The later prompt split moved the shared routing rule into
each lens role template, where the agent that classifies a finding reads it; the goal
now contains only lens-specific task text.[^split][^lenses] Widening
`CATEGORY_ALIASES` to accept `cleanliness` was the cheap alternative and was rejected:
it would have let the taxonomy settle wherever the model happened to land, and the
pond#237 four-way comparison keys on category to align three reviewers who share no
line numbers. The `convention` entry in the alias table was removed in the same change,
because the routing rule settles the reading it existed to allow.[^grader]

All four cases now accept exactly one category. That is a narrower bar than before, not a
wider one.

[^run]: the run where both failures were taxonomy and neither was detection
[^coinflip]: the earlier run that filed the identical finding under an accepted label
[^lenses]: the current lens-role routing rule
[^split]: the prompt split that moved the rule out of the goal
[^grader]: the grader, whose alias table is the join between corpus vocabulary and review vocabulary

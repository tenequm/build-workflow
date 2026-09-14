---
type: Decision
title: A finding names the identifier it is about, because a line anchor does not survive the comparison it is written for
description: /review-pr's findings carry the function, constant, config key or filename they concern in an `identifier` field of the report's json block, not only `file:line` - because the reviews they are compared against are written from a different checkout, where no line number resolves. Three smoke runs reported the same planted defect correctly and scored as failures; stating the rule in prose was not enough, because a model paraphrases its claim to the shortest true sentence and that sentence drops the name.
tags: [review-pr, goal-text, corpus, evaluation]
status: stable
generated: { by: claude-code/opus-5, at: "2026-09-14T15:05:00Z" }
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
  - id: third
    resource: "the corpus run of 2026-09-14T14:39Z on case-01-off-by-one, workspace /tmp/review-eval-20260914T143905Z, scored MISSED in 485.3s. Its report names `calculate_total_pages()` in the prose finding and carries the name in an `identifier` key the contract did not define, while the block's `claim` reads only 'Exact multiples of per_page are reported with one phantom extra page.' Replayed under the schema field the run produced RECOVERED."
    title: the run where the name was present and the grep still failed
---

# Decision

Every finding states the identifier it concerns - the function, method, class,
constant, config key, flag or filename - spelled as the code spells it, in an
`identifier` field of the report's json block and in the prose claim.
`file:line` stays, as an address; it is no longer the whole identification.

The field is the load-bearing half. The rule was first written as prose alone,
requiring the name in `claim` or `evidence`, and that failed on its first
outing - see below.

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

## Why prose was not a durable carrier

The rule went into the goal text as a prose requirement - the name belongs in
`claim` or `evidence`, the author's choice which. The next run failed anyway, and
the way it failed is the whole finding.[^third]

The reviewer had understood the rule. Its prose finding opens
"`calculate_total_pages()` adds a phantom page when `total_items` is an exact
multiple of `per_page`". But the json block's `claim` - the only text the grader
reads - had been paraphrased down to the shortest true sentence, and the shortest
true sentence drops the name. The model then put the name in an `identifier` key
it invented, because a name is structured data and it did not want to smuggle it
into a sentence. It also dropped `evidence`, which the contract required.

Two lessons, both general:

- **A fact that must be machine-read needs a slot, not a sentence.** "Put X in
  your prose" survives exactly as long as nothing compresses the prose, and
  summarisation compresses prose by construction. An offered field is where a
  model will put a name.
- **When a model invents a field, it is reporting a gap in the schema.** The
  remedy was to promote the invented key into the contract rather than to argue
  the model out of it. The grader now compares that field exactly, and the fuzzy
  substring search it replaced is gone for the identifier half.

Two of the four corpus cases plant defects with no single named subject - an
injected comment, an omission from a coverage list - and declare no expected
identifier; they are still graded on keywords. The field is required of the
reviewer everywhere and asserted by the case only where the defect has a name.

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

### The second round did edit two expectations, and that needs saying plainly

`case-01` and `case-02` moved their subject's name out of `must_mention` and into
a new `identifier` key. That is an edit to a frozen case, made after those cases
failed, which is exactly the shape the freeze rule exists to catch - so the test
is whether it lowered the bar.

It raised it. `must_mention` succeeds on a substring found anywhere across three
concatenated prose fields, case-insensitively, so `calculate_total_pages` would
have matched a sentence that merely quoted a nearby line containing it.
`identifier` is one field, compared whole and case-sensitively. Nothing that
failed before passes now for being asked less; what changed is where the
reviewer must put the answer, which is the rule this decision is about. The
keywords that were genuinely prose assertions - `per_page`, `test` - stayed in
`must_mention` and are still grepped.

[^grading]: the pond#237 grading rules, fixed before reviewer C existed
[^smokes]: two lanes, same omission, both scored as failures
[^freeze]: the corpus freeze rule, which forbade the easy fix
[^goal]: where the rule now lives
[^third]: the run where the name was present and the grep still failed

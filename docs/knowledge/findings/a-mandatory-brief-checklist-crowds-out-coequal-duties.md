---
type: Finding
title: A mandatory checklist added to a lens brief crowds out its other duties, and the model says so while doing it
description: After the implementation lens gained a mandatory two-phase authority-file audit, it went 6/6 on authority-shaped defects while dropping plain code defects it had explicitly identified in its own reasoning as "a logic bug, rather than a claim vs. implementation conflict" - a structured mandate narrows a model's perceived scope, so every added checklist must restate what remains coequal.
tags: [review-pr, prompts, lenses, eval]
status: stable
generated: { by: claude-code/fable-5, at: "2026-09-11T13:55:00Z" }
sources:
  - id: evalrun
    resource: "Synthetic-corpus eval run of 2026-09-11 (ledger rows in docs/review-ledger/evals.jsonl): bar tier 6/6 found, floor tier 3/8"
    title: The run that measured both effects at once
  - id: lens
    resource: ../../../skills/review-pr/templates/lens-implementation.md
    title: The lens template carrying the two-phase audit
---

# What happened

The implementation lens was given a mandatory two-phase authority-file protocol
(extract normative claims per file, then audit every hunk against them) to close a
measured miss class: defects visible only after reading a governance document end to
end. It worked - the eval's bar tier, six cases modeled on that miss class, went six
for six.[^evalrun]

The same run's floor tier - trivial, objective, in-hunk defects - dropped to three of
eight. The reasoning traces show the mechanism precisely: on an off-by-one in a
ceiling division, the lens *identified the bug*, then discarded it as "a logic bug,
rather than a claim vs. implementation conflict". On false test-coverage claims, two
lenses noticed the diff touched no test files and each dismissed it as the other's
scope. The model did not fail to see; it obeyed the brief's new emphasis and
concluded its old duties were no longer its job.[^evalrun]

# The rule

A structured mandatory protocol is the strongest scope signal a brief can send: it
implicitly demotes everything it does not mention. When adding one, restate the
remaining duties as explicitly coequal - and keep a regression tier in the eval corpus
that measures the duties the new protocol does NOT serve, because the crowding effect
is invisible on the metric the protocol was built to move.

---
type: Decision
title: Cost figures are observability, never control flow
description: The review workflow deleted its spend bound, reservation ledger and parks on cost evidence - runaway protection is per-session budget, turn and wall-clock ceilings - and dollar figures are derived after the run from pond token counts priced by a vendored provider-rate registry, labeled a list-price floor on subscription lanes.
tags: [review-pr, cost, pond, bounds]
status: stable
generated: { by: claude-code/fable-5, at: "2026-09-11T12:00:00Z" }
sources:
  - id: burn
    resource: /findings/review-session-cost-figures-are-not-invoices.md
    title: The figures the removed bookkeeping published were not costs
  - id: accounting
    resource: https://github.com/tenequm/pond/blob/main/docs/other/2608-27-token-usage-accounting.md
    title: pond token-usage accounting - dedup rules, per-harness paths, pricing
  - id: registry
    resource: https://github.com/BerriAI/litellm/blob/main/model_prices_and_context_window.json
    title: LiteLLM model prices, the source ccusage uses, snapshot vendored as templates/registry.json
---

# Decision

The driver-side money machinery - a stage spend bound, full-reservation charging for
unmetered transports, and Parks on missing, malformed or regressing ACP cost
evidence - is deleted from /review-pr. Every one of those mechanisms could stop or
void real work over figures that were never invoices,[^burn] on lanes a subscription
already covers. What remains as control is per-session: a budget ceiling the Claude
bridge enforces itself, turn limits, per-session timeouts, and one batch wall clock.

Cost reporting remains, as observability computed after the run: the capture stage
resolves every session in pond and prices its token usage - deduplicated by provider
message id for Claude, final cumulative totals for codex, per-call sums for agy[^accounting] -
from a vendored provider/model rate registry.[^registry] A model absent from the
registry prices to null, never zero, and the output is labeled a list-price
equivalent and a floor. The blind judge in /build-run keeps its strict cost-evidence
contract; the tolerance is a parameter, not a global weakening.

**Why:** two paid runs demonstrated the machinery's failure modes - a park over a
malformed cost update, budgets shaping review behaviour (a lens reporting 93% of its
ceiling), and a published "$29 spend" that was mostly the workflow's own reservation
arithmetic. The user's framing settled it: optimize for result quality; costs on
subscription lanes are not the axis.

**How to apply:** a new bound in this workflow must name what it protects against in
wall-clock or session terms, never dollars; a new dollar figure must come from pond
after the fact and carry its floor label. The capture substrate it rides on is
[the per-run pond store](/decisions/per-run-pond-store-for-capture.md).

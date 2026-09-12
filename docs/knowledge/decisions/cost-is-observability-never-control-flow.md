---
type: Decision
title: Cost figures are observability, never control flow
description: A bound this workflow adds names what it protects against in sessions, turns or wall clock and never in dollars, because no figure available at runtime is an invoice; dollar amounts are derived after the run from pond token counts priced by a provider-rate registry and labeled a list-price floor, and the dollar-reading ceilings already inside /build-run's ceremony are the deliberate, non-extensible exception.
tags: [build-run, cost, pond, bounds]
status: stable
generated: { by: claude-code/opus-5, at: "2026-09-11T19:40:00Z" }
sources:
  - id: paid
    resource: "Two paid runs of the retired driver-owned review pipeline, 2026-09-10/11: a park over a malformed cost update, a lens shaping its behaviour around its ceiling, and a published spend figure that was mostly the workflow's own reservation arithmetic (the code and its ledger are in git history)"
    title: The failure modes that settled this
  - id: accounting
    resource: https://github.com/tenequm/pond/blob/main/docs/other/2608-27-token-usage-accounting.md
    title: pond token-usage accounting - dedup rules, per-harness paths, pricing
  - id: registry
    resource: https://github.com/BerriAI/litellm/blob/main/model_prices_and_context_window.json
    title: LiteLLM model prices, the source ccusage uses
  - id: ceremony
    resource: ../../../skills/build-run/scripts/operator_driver/ceremony.py
    title: "ceremony.py:108 reserved_usd, :192 park when measured cost exceeds the reservation"
  - id: engine
    resource: ../../../skills/build-run/scripts/operator_driver/engine.py
    title: "engine.py:29 cost_for over the native cost ledger, :154 the whole-build run_budget_usd bound"
  - id: bridge
    resource: ../../../skills/build-run/scripts/operator_driver/acp.py
    title: "acp.py:39 the Claude bridge's per-session --budget, :144-155 the require_cost parks on the claude transport"
---

# Decision

Dollars are something this workflow measures, not something it decides on.

1. **A new bound never reads a dollar amount.** It names what it protects against
   in sessions, turns or wall clock. Money cannot be a stop condition on real work,
   because nothing available at runtime is an invoice: a reservation is an estimate
   the workflow made up, a bridge's figure is list price regardless of whether the
   account behind it is per-token or a subscription, and an engine's own ledger is
   partial by construction.
2. **A dollar figure is produced after the run and labeled a floor.** It is derived
   from pond token counts - deduplicated by provider message id for Claude, final
   cumulative totals for codex, per-call sums for agy[^accounting] - priced from a
   provider/model rate registry.[^registry] A model absent from the registry prices
   to null, never zero, and the output is reported as a list-price equivalent and a
   floor, never as spend.

**Why:** the two paid runs that exercised the retired review pipeline demonstrated
every failure mode at once - a park that voided good work over a malformed cost
update, a budget ceiling visibly shaping a model's behaviour, and a headline spend
figure that was mostly reservation arithmetic.[^paid] The operator's framing settled
it: optimise for result quality; on subscription and free lanes, cost is not the axis.

# What /build-run already reads in dollars

The law is prospective and does not silently rewrite the judge ceremony that
predates it. Three existing bounds do read a dollar amount and stay as they are:

- the Claude bridge's per-session `--budget`, which the session enforces itself;[^bridge]
- the ceremony's park when a judge's measured cost exceeds the spend reserved for
  it, plus the strict cost-evidence contract on the `claude` transport - missing,
  malformed or backwards-moving cost evidence parks;[^ceremony][^bridge]
- the whole-build bound over the engine's native cost ledger, which charges an
  unmetered ceremony its full reservation rather than reading an absent number as
  zero.[^engine]

Each is runaway protection over one session or one run's own metered evidence, and
the blind judge's economics depend on the contract; the tolerance is a parameter of
that ceremony, not a global weakening. Extending them - a new park on cost evidence,
a dollar threshold on a new stage - is what this decision forbids.

# How to apply

A bound proposed for this workflow states its protection in wall-clock, turn or
session terms. A dollar figure in a report, ledger row or summary is computed after
the run from pond and carries its floor label. Note that no code in this repository
performs that pricing any more - the module that did was deleted with the review
driver - so the derivation is done out of band with pond's own accounting, and the
rate registry above is the reference for what to price against.

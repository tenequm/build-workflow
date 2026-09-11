---
type: Finding
title: A review run's dollar figures are a reservation and a usage meter, never an invoice
description: Summing what the workflow calls charged spend produced a number twice reported as provider cost that was neither - most of it was full reservations charged against agents that reported nothing, and the remainder was the Claude bridge's list-price estimate, which it emits identically whether the account behind it is per-token or a subscription.
tags: [review-pr, cost, evidence, acp]
status: stable
generated: { by: claude-code/opus-5, at: "2026-09-11T09:20:00Z" }
sources:
  - id: measured
    resource: "Measured 2026-09-11 across two paid /review-pr runs: per-session receipts with their metered flag, against the auth mode configured for each CLI on the operator host"
    title: The receipts and the auth modes behind them
  - id: runner
    resource: ../../../skills/review-pr/scripts/review_pr/runner.py
    title: The receipt fields - cost_usd, metered, charged_usd
  - id: acp
    resource: ../../../skills/build-run/scripts/operator_driver/acp.py
    title: The transcript reader, and why an unmetered transport settles at its reservation
---

# Three different numbers

A session receipt carries three things that are easy to read as one:

| field | means |
|---|---|
| `cost_usd` | what the adapter reported, or `null` when it reported nothing |
| `metered` | whether it reported at all |
| `charged_usd` | what the spend bound counted - the reported figure, or **the whole reservation** when nothing was reported |

Only the first is ever close to money, and even then only conditionally. Summing the
third and calling it spend is what produced a figure reported twice as provider cost
that was not one: of $15.33 counted, $10.00 was reservations charged against five
sessions that reported nothing at all.[^measured]

# Which agents report, and what the number means

- **The Claude bridge** reports a cumulative USD figure the SDK computes from token
  counts and list pricing. It emits that figure regardless of the account behind it, so
  on a subscription it is a **usage meter against quota**, not a charge. Nothing in the
  ACP stream distinguishes the two cases; only the CLI's own auth configuration does.
- **Codex on `auth_mode = chatgpt`** and the **Antigravity ACP lane** report no cost.
  That is not a gap to work around - it is what subscription-backed means here, and the
  bound deliberately charges their full reservation rather than reading an absent number
  as zero.[^acp]

The consequence for evidence: a run where most sessions are subscription-backed has a
`charged` total dominated by ceilings the operator chose, and a `reported` total that
measures quota consumption on one family only. Neither answers "what did this cost",
and no arrangement of them does. A provider's own billing is the only thing that can.

# What the output says now

Evidence carries `reported_usd` and `reserved_usd` separately, with `metered_sessions`
alongside, and the batch summary's column is labelled *reported*.[^runner] The reason to
keep both is that they answer different real questions - "is a session running away"
needs the reservation, "how much quota is this workflow consuming" needs the meter - and
the reason to keep them apart is that adding them together answers neither.

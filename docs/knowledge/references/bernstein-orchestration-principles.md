---
type: Reference
title: Bernstein's orchestration principles, distilled for reuse here
description: The engine's architecture docs reduce to one law - models draft and execute at the edges, code decides what runs next - enforced by the import graph, compiled plans, exhaustive FSM tables, a hash-chained intent-confirm WAL that lets a restart re-derive instead of re-decide, and judges that trust signals over agent claims.
tags: [bernstein, orchestration, determinism, state, verification]
status: stable
stale_after: "2027-03-11T00:00:00Z"
generated: { by: claude-code/fable-5, at: "2026-09-11T00:00:00Z" }
sources:
  - id: why
    resource: https://github.com/sipyourdrink-ltd/bernstein/blob/65b7e0d7/docs/architecture/WHY_DETERMINISTIC.md
    title: WHY_DETERMINISTIC - the rag_challenge evidence and the boundary
  - id: adr11
    resource: https://github.com/sipyourdrink-ltd/bernstein/blob/65b7e0d7/docs/decisions/011-model-drafts-human-signs.md
    title: ADR-011, model drafts / human signs (supersedes ADR-006)
  - id: persist
    resource: https://github.com/sipyourdrink-ltd/bernstein/blob/65b7e0d7/docs/architecture/state-persistence.md
    title: State persistence - WAL, idempotency, crash resume
  - id: lifecycle
    resource: https://github.com/sipyourdrink-ltd/bernstein/blob/65b7e0d7/docs/architecture/LIFECYCLE.md
    title: The three exhaustively tabulated state machines
  - id: quality
    resource: https://github.com/sipyourdrink-ltd/bernstein/blob/65b7e0d7/docs/architecture/quality-pipeline.md
    title: Quality pipeline - signals, gates, fresh-context review
  - id: phases
    resource: https://github.com/sipyourdrink-ltd/bernstein/blob/65b7e0d7/docs/concepts/phase-pipeline.md
    title: Phase pipeline - fresh agent per phase, structured handoff
---

# Reference

Bernstein's architecture reduces to one law, stated in ADR-011:[^adr11]

> A model may draft an artefact a human must sign. It may never decide what
> runs next, which agent gets it, whether it is retried, or when it ends.

The rationale is empirical, not aesthetic: a predecessor system put an LLM
manager in the loop and it fell asleep, starving 12 agents for 47 hours; 350
lines of anti-sleep prompting failed, and the conclusion was structural -
"the orchestration layer must be code, not a model".[^why]

# The principles, each with its mechanism

1. **The boundary is the import graph, not a policy.** The orchestrator class
   imports no LLM client, so the forbidden decisions (ordering, assignment,
   retry, lifecycle end) cannot drift back to a model without a diff that
   shows it.[^why]
2. **Multi-phase work is compiled to data before anything runs.** Plans
   become task rows with explicit dependency lists; conditionals and retry
   loops are declarative fields evaluated by an AST-whitelisted evaluator.
   After compilation, a deterministic tick loop walks the graph - the same
   plan replays to a byte-identical task graph.[^why]
3. **Every lifecycle is an exhaustive table.** Task, session and turn each
   have a total FSM; a transition not in the table raises, and every
   transition emits a typed event with actor and reason, which is what makes
   audit and replay possible.[^lifecycle]
4. **State is files, and writes are intent-confirm.** Run state lives in
   editable files, decisions in a hash-chained append-only WAL fsynced per
   entry: record the intent, perform the side effect, confirm. A restart
   re-derives - replaying uncommitted intents through an idempotency store -
   and never re-decides. Derived indexes follow the "absent or right" rule:
   an index that cannot be written correctly is deleted, converting a
   dangerous half-state into one slow rescan.[^persist]
5. **Phases hand off artefacts, never transcripts.** Each phase is a fresh
   short-lived agent whose prompt is seeded with the prior phase's structured
   JSON summary only. Context rot cannot accumulate because nothing
   long-lived exists to rot - "a dead agent cannot fall asleep".[^phases]
6. **Verification trusts signals, not claims, and fails closed.** The
   orchestrator - never the agent, never a driver model - launches judges
   after an agent exits. Declarative completion signals are checked
   mechanically; a reviewer runs in a fresh session on a distinct model and
   sees only spec, diff and test output; an unparseable review verdict maps
   to fail, so a reviewer outage never green-lights a merge. The hardest
   case, a claim that nothing was found, passes only when the recorded
   coverage walk hash-matches lineage - absence is recorded, never
   silent.[^quality]
7. **Determinism has admitted edges.** Adaptive parallelism and the
   escalation bandit make routing history-dependent, dynamic re-planning
   mid-run is deliberately impossible, and CLI-adapter LLM traffic is outside
   replay - the docs state each cost rather than hiding it.[^why]

# What this bundle already holds against it

[Review sessions as driver-owned ceremonies](/decisions/review-sessions-are-driver-owned-ceremonies.md)
and [the phase boundary between engine runs](/decisions/phase-boundary-between-engine-runs.md)
are applications of principles 1 and 6.
[Engine bookkeeping is not delivery proof](/findings/engine-bookkeeping-is-not-delivery-proof.md)
is principle 6 learned independently. Where /review-pr still falls short of
principles 3 and 4 - stage products held in one process's memory, resume
meaning re-execution - is an open gap, not a disagreement.

[^why]: WHY_DETERMINISTIC - the rag_challenge evidence and the boundary
[^adr11]: ADR-011, model drafts / human signs
[^persist]: State persistence - WAL, idempotency, crash resume
[^lifecycle]: The three exhaustively tabulated state machines
[^quality]: Quality pipeline - signals, gates, fresh-context review
[^phases]: Phase pipeline - fresh agent per phase, structured handoff

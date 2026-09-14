---
type: Finding
title: The engine repository grows additively because its own fleet authors it
description: Bernstein is written by agent fleets under an append-only editing convention, so modules only lengthen and nothing consolidates - which is why its documentation records intent rather than wiring, and why the repository can be locally rigorous and globally unnavigable at the same time.
tags: [bernstein, engine-audit, verification-discipline, agent-authored-code]
status: stable
stale_after: "2027-03-11T00:00:00Z"
generated: { by: claude-code/opus-5, at: "2026-09-11T13:51:20Z" }
sources:
  - id: shape
    resource: local clone of https://github.com/sipyourdrink-ltd/bernstein at 65b7e0d73, measured 2026-09-11
    title: Repository shape measurement
  - id: policy
    resource: https://github.com/sipyourdrink-ltd/bernstein/blob/65b7e0d73/src/bernstein/core/security/audit_chain.py
    title: Concurrent-edit policy docstring, lines 10-22
  - id: authorship
    resource: git log of the same clone since 2026-08-01 (author tallies)
    title: Authorship measurement
  - id: session
    resource: operator's pond archive, session c9ebe8dc-f5f3-4c1c-8d85-b5b9c6847730 (codebase-character analysis, 2026-09-09)
    title: Analysis session
---

# Finding

Measured at engine commit `65b7e0d73` (2026-09-11): **870,822 lines of Python
outside tests, across 2,278 files**, with the largest modules at 10,045
(`core/security/audit_chain.py`), 7,513 (`core/orchestration/orchestrator.py`)
and 7,067 (`core/agents/spawner_core.py`) lines.[^shape] Since 2026-08-01 the
tree took **1,341 commits** - the maintainer at 623 and the project's own
`bernstein-orchestrator[bot]` second at 132, ahead of every human
contributor.[^authorship]

The convention that produces this shape is written down in the module that
grew largest:[^policy]

> New event types should be added below as `EVENT_<UPPER_SNAKE>` string
> constants -- never edit existing entries.
>
> **Concurrent-edit policy** - Sibling agents may extend this module with
> additional event-type constants and helper functions; the
> `AuditChainStore` class itself is treated as the stable surface.

That is the correct concurrency discipline for many writers with no shared
working memory: extending a file merges, restructuring it conflicts. Its
consequence is that the repository can only accrete. Consolidation passes -
the thing human codebases rely on to stay navigable - are the one edit class
the authoring process forbids, while the marginal cost of a new feature is
near zero, so scope grows at the same time.

# Why it matters here

This is the mechanism behind the defect class this bundle keeps recording.
Documentation, enums, routes and CLI flags are cheap to add and never
retired, so a declared surface is evidence of intent, not of wiring - see
[a documented Bernstein surface is not a wired one](declared-but-unwired-engine-surfaces.md),
and the same shape in
[plan-file completion signals are silently dropped at task POST](plan-post-drops-completion-signals.md).
The inverse also holds: the individual modules are unusually well specified
(the payments package states its money-never-touches-float and
reject-don't-normalize invariants with the reasoning attached), and tests
track source roughly one to one. Local rigour and global drift are not in
tension here; they are both outputs of the same process.

# Rule

Read this repository as a record of what agents were asked to build, never as
a description of what runs. Trust a module's own invariants; verify every
cross-module claim at the production call site. Expect the numbers above to
grow, never to shrink, unless a ratchet is introduced - see the general law
in the operator's cross-project bundle (agent-codebase entropy reverses only
under CI ratchets).[^session]

[^shape]: [Repository shape measurement](https://github.com/sipyourdrink-ltd/bernstein) - local clone at 65b7e0d73, measured 2026-09-11.
[^authorship]: Authorship measurement - git log of the same clone since 2026-08-01.
[^policy]: [Concurrent-edit policy docstring, lines 10-22](https://github.com/sipyourdrink-ltd/bernstein/blob/65b7e0d73/src/bernstein/core/security/audit_chain.py)
[^session]: Analysis session - operator's pond archive, session c9ebe8dc (2026-09-09).

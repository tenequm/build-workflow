---
type: Reference
title: How upstream Bernstein recruits contributors and who pays for the compute
description: Contributing to Bernstein is the product's own demo - the volunteer-workers program is both the headline feature and the entry point in CONTRIBUTING.md, contributors run their own agents on their own subscriptions, and 28 of 74 CI workflows sit on the project's own runners; the result is an abnormal contributor-to-star ratio with merge authority still held by one person.
tags: [bernstein, upstream, governance, volunteer-program]
status: stable
stale_after: "2027-03-11T00:00:00Z"
generated: { by: claude-code/opus-5, at: "2026-09-11T13:51:20Z" }
sources:
  - id: contributing
    resource: https://github.com/sipyourdrink-ltd/bernstein/blob/main/CONTRIBUTING.md
    title: "CONTRIBUTING.md - \"Start here: the volunteer workers program\" (#3863)"
  - id: manifest
    resource: https://github.com/sipyourdrink-ltd/bernstein/blob/main/docs/reference/volunteer-manifest.md
    title: The .bernstein/volunteer.json manifest - sandbox, network allowlist, ceilings, receipt binding
  - id: package
    resource: local clone at 65b7e0d73, src/bernstein/core/volunteer/ and src/bernstein/cli/commands/volunteer_cmd.py
    title: Volunteer package and CLI surface
  - id: metrics
    resource: GitHub API for sipyourdrink-ltd/bernstein, measured 2026-09-11 (repo stats, contributor list, last 200 merged pull requests)
    title: Repository and throughput measurement
  - id: session
    resource: operator's pond archive, session c9ebe8dc-f5f3-4c1c-8d85-b5b9c6847730 (contributor-economics analysis, 2026-09-09)
    title: Analysis session
---

# The anomaly

Created 2026-03-22, the repository had 1,160 stars, 158 forks and **100
contributors** when measured on 2026-09-11.[^metrics] A contributor count near
9% of stars is roughly an order of magnitude above the norm; projects with
twenty times the stars rarely reach fifty contributors. Three mechanisms
produce it, and all three are visible in the repository itself.

# 1. Contribution is the product's own demo

`CONTRIBUTING.md` does not open with a style guide - it opens with
"**Start here:** the volunteer workers program", described as donated AI
compute working through open-source backlogs, with every sub-issue sliced to
be workable alone and design comments on the RFC counted as
contributions.[^contributing] The `core/volunteer` package that reads as scope
sprawl from the outside is the funnel: a project declares what a task may do
in a `.bernstein/volunteer.json` manifest - sandbox backend, network
allowlist, wall-clock and memory ceilings - a donor runs
`bernstein volunteer browse --budget <minutes>` on their own machine with no
account and no coordinator, the donor's own limits may only narrow the
manifest, and the receipt binds the result to the containment it ran
under.[^manifest][^package] Using the tool and contributing to it are the same
act.

# 2. Every user arrives agent-equipped

The audience self-selects for people who run agent fleets, so the cost of a
pull request collapses: the contributor's own agents produce the fix on the
contributor's own subscription, and the maintainer pays for none of it. The
operator's own path is the template - bugs hit as a user, fixes produced by
his executors, roughly ten merged pull requests over six weeks, then a core
reviewer invitation.[^session] For the volunteer program this is explicit
("donated AI compute"); for ordinary pull requests it is an inference from the
audience and from that one measured path, not something the repository
states.[^contributing][^session]

The maintainer's own lane runs the same way. Bernstein's adapters spawn
`claude` and `codex` CLI processes - flat-rate subscription capacity rather
than metered API billing - and the project's GitHub App account authors merge
queue and hygiene pull requests. CI was moved off GitHub's meter too: **28 of
74 workflows** run on self-hosted runners.[^package][^metrics]

# 3. Governance converts drive-bys into committers

A quorum roster, a `needs-committer-review` label and a CODEOWNERS structure
give community members merge-blocking review power. The ladder is real but
the trigger is not yet distributed: of the last 200 merged pull requests,
**195 were merged by the maintainer** and 5 by one other committer. Authorship
is far more distributed than merge authority - maintainer 52, then 42, 25, 17,
10, with bots at 18 and 8 - so external humans together ship roughly twice the
maintainer's volume while he still performs nearly every merge.[^metrics]

# Why this is worth knowing

It explains the velocity this bundle's other concepts describe - the fleet
authorship behind
[the engine repository grows additively](../findings/engine-repo-grows-additively.md),
and the review machinery in
[how upstream reviews its own pull requests](upstream-review-automation.md).
It also sets the expectation for a reviewer seat: throughput is funded by
contributors and will keep climbing, while the review queue it feeds is a
claim on the reviewer's attention, not on the maintainer's budget.

[^contributing]: [CONTRIBUTING.md - "Start here: the volunteer workers program" (#3863)](https://github.com/sipyourdrink-ltd/bernstein/blob/main/CONTRIBUTING.md)
[^manifest]: [The .bernstein/volunteer.json manifest - sandbox, network allowlist, ceilings, receipt binding](https://github.com/sipyourdrink-ltd/bernstein/blob/main/docs/reference/volunteer-manifest.md)
[^package]: Volunteer package and CLI surface - local clone at 65b7e0d73, `src/bernstein/core/volunteer/` and `src/bernstein/cli/commands/volunteer_cmd.py`.
[^metrics]: Repository and throughput measurement - GitHub API for sipyourdrink-ltd/bernstein, 2026-09-11.
[^session]: Analysis session - operator's pond archive, session c9ebe8dc (2026-09-09).

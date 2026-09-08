---
type: Decision
title: Bernstein is tracked upstream-first through a minimal rebased fork
description: The engine fork carries only fixes upstream does not yet have, rebuilt from upstream main whenever upstream absorbs some; every fix is submitted upstream as a small single-topic PR. Fully absorbed 2026-09-08 - the workflow now installs a source build of upstream main, and the discipline stands ready if a new engine defect appears.
tags: [bernstein, fork, upstream, dependencies]
status: stable
generated: { by: claude-code/fable-5, at: "2026-09-08T08:25:00Z" }
sources:
  - id: refs-update
    resource: https://github.com/tenequm/build-workflow/commit/cbdd972
    title: "docs: point fork references at fork/main-plus-fixes (upstream main + 3 fixes)"
  - id: fork-branch
    resource: https://github.com/tenequm/bernstein/tree/fork/main-plus-fixes
    title: The carrying branch (upstream main plus the unmerged fixes)
  - id: absorbed
    resource: https://github.com/sipyourdrink-ltd/bernstein/pulls?q=is%3Apr+author%3Atenequm+is%3Amerged
    title: Merged upstream PRs from this project
  - id: last-fix
    resource: https://github.com/sipyourdrink-ltd/bernstein/pull/5619
    title: The last carried fix (uncommitted-work veto), merged 2026-09-08
---

# Decision

The fork branch (`fork/main-plus-fixes` on `tenequm/bernstein`) is upstream
`main` plus only the fixes upstream does not yet carry - nothing
else.[^fork-branch] Every engine defect the workflow hits is fixed locally,
then submitted upstream as a small single-topic PR with a regression test
that fails on upstream's base. When upstream absorbs fixes, the branch is
rebuilt from current `main` with only the survivors cherry-picked, and the
stale remote branch is force-pushed (same name, so README instructions stay
valid).[^refs-update] The exit condition is explicit: once a PyPI release
contains every carried fix, the fork is deleted and the workflow installs
stock Bernstein.

# Outcome (2026-09-08)

Upstream absorbed everything: all 11 PRs from this project merged, the last
(#5619, the uncommitted-work veto) on 2026-09-08.[^absorbed][^last-fix] A
content-level diff of `fork/main-plus-fixes` against upstream `main` showed
main carrying every fork change in equal or refined form (e.g. the veto
landed with tighter `.sdd/` scoping) and nothing fork-only remaining;
`bernstein_herdr`'s suite passed against a build of current main. The
workflow now clones upstream and installs a source build of `main` directly.
The fork branch is retired. The final exit step - installing from PyPI -
still waits on a release newer than v3.19.1 (2026-09-03), which predates the
last four fixes. If a new engine defect appears, this discipline restarts:
fix locally, carry minimally, submit upstream, retire on absorption.

# Why minimal, why rebuilt

A long-lived fork rots in two directions: its own commits conflict with a
fast-moving upstream (Bernstein merges dozens of commits per day), and the
companion package (`bernstein_herdr`) imports engine internals whose line
numbers and regexes are cited from a specific version. The 2026-09-07
reconciliation measured the cost of not rebasing: the fork had accumulated
20 commits, of which 17 were already on upstream `main` in reshaped form -
dead weight that made every future rebase and every drift question harder.
Rebuilding cut it to 3.[^refs-update][^absorbed]

Upstreaming aggressively works here because the maintainers demonstrably
merge small, evidence-backed PRs within days and have twice fixed our
branches themselves rather than bounce them.[^absorbed] The corollary
discipline: fixes stay single-topic and carry fail-on-base tests, because
that is the shape upstream's review machinery verifies (see
[contributing conventions](/references/contributing-to-bernstein.md)).

[^refs-update]: docs: point fork references at fork/main-plus-fixes
[^fork-branch]: The carrying branch on the fork
[^absorbed]: Merged upstream PRs from this project
[^last-fix]: The last carried fix (uncommitted-work veto), merged 2026-09-08

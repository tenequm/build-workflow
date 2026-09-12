---
type: Decision
title: Bernstein is tracked upstream-first through a minimal rebased fork
description: The engine fork carries only fixes upstream does not yet have, rebuilt from upstream main whenever upstream absorbs some; every fix is submitted upstream as a small single-topic PR. Fully absorbed 2026-09-08 - the workflow now installs a source build of upstream main, and the discipline stands ready if a new engine defect appears.
tags: [bernstein, fork, upstream, dependencies]
status: stable
generated: { by: claude-code/opus-5, at: "2026-09-11T23:25:00Z" }
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
  - id: measured-2609-11
    resource: "file-by-file comparison on 2026-09-11 of ~/.local/share/uv/tools/bernstein/lib/python3.13/site-packages/bernstein against upstream main at ebad8f5b3; git log -S run over the upstream history for each hunk"
    title: four hunks in the installed build that upstream history does not contain
  - id: anchors
    resource: "skills/build-run/scripts/prepare-engine.py, its PATCHES table and the `source.count(before) != 1` guard; re-measured 2026-09-11 by applying it to a fresh checkout of upstream main at ebad8f5b3 and re-running it with --check"
    title: the patch set is anchor-based, so it reapplies onto a moved file or fails loudly
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

# Addendum (2026-09-11): the installed build is not stock

A file-by-file comparison of the build actually installed on this host against
upstream `main` at `ebad8f5b3` found 12 differing files, of which nine are
upstream being newer. The other three carry the four local hunks that
`skills/build-run/scripts/prepare-engine.py` applies, and `git log -S` finds
none of them anywhere in upstream history:[^measured-2609-11]

- `core/orchestration/orchestrator.py` - the CLOSED term in
  `_had_any_terminal_task` (see
  [the CLOSED quiescence finding](/findings/merged-tasks-close-and-stall-quiescence.md)),
  and a `BERNSTEIN_RESPONSE_CACHE` kill switch.
- `core/config/seed_parser.py` - a `GatePluginRegistry` fallback so an unknown
  `quality_gates.pipeline[].name` is not rejected.
- `core/git/git_basic.py` - the `BERNSTEIN_OPERATOR_LOCAL_ONLY` early return in
  `safe_push`, so an operator phase build never fetches, rebases or pushes (see
  [the merge-back finding](/findings/native-merge-back-pushes.md)).

That last file is the shape to expect on every future upgrade: it carries a
local hunk **and** an upstream change to a different function in the same file
(`resolve_default_branch`, upstream PR #5778). The file partition is therefore
not a clean local/upstream split, and a patch set that reasoned in whole files
rather than anchors would have silently dropped a hunk. `prepare-engine.py`
survives this because each patch is an exact before/after pair asserted unique
(`source.count(before) != 1` raises), not a line range or a whole-file
replacement - so an upstream edit elsewhere in a patched file is invisible to
it, and an upstream edit *at* the anchor fails loudly instead of
silently.[^anchors]

The installed distribution also reports itself as 3.19.1 while its files are a
`main` snapshot of about 2026-09-08, so the version string does not identify
what is running. Neither observation changes the decision above - upstream-first
with a minimal carry is still the discipline - but the 2026-09-08 outcome's
"nothing fork-only remaining" is no longer true of the installed artifact, and
any engine upgrade must re-apply these four or silently lose them. How they
came to be installed was not determined.

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
[^measured-2609-11]: Four local hunks measured in the installed build, 2026-09-11
[^anchors]: the patch set is anchor-based, not line- or file-based

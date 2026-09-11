---
type: Reference
title: How upstream Bernstein reviews its own pull requests - the maintainer's automation stack
description: Upstream review is five CI layers, not a human workflow - a quorum script on the default branch owns the charter arithmetic (GitHub's required-approvals rule is off since 2026-09-09), the deep-review label runs Bernstein on itself with a $3 budget, and the maintainer's own reviewing happens as agent-driven API bursts under his account.
tags: [bernstein, upstream, review, governance, ci]
status: stable
stale_after: "2026-12-11T00:00:00Z"
generated: { by: claude-code/fable-5, at: "2026-09-11T00:00:00Z" }
sources:
  - id: prreview
    resource: https://github.com/sipyourdrink-ltd/bernstein/blob/main/.github/workflows/bernstein-pr-review.yml
    title: bernstein-pr-review.yml (deep-review label, self-review via the root action)
  - id: quorum
    resource: https://github.com/sipyourdrink-ltd/bernstein/blob/main/.github/workflows/quorum.yml
    title: quorum.yml (org-ruleset-pinned required workflow)
  - id: quorumscript
    resource: https://github.com/sipyourdrink-ltd/bernstein/blob/main/scripts/quorum_check.py
    title: quorum_check.py (the charter arithmetic, rules 0-5 in its docstring)
  - id: steward
    resource: https://github.com/sipyourdrink-ltd/bernstein/blob/main/.github/workflows/area-steward-review.yml
    title: area-steward-review.yml (docs steward routing on pull_request_target)
  - id: decompose
    resource: https://github.com/sipyourdrink-ltd/bernstein/blob/main/.github/workflows/bernstein-issues-decompose.yml
    title: bernstein-issues-decompose.yml (sender-gated pipeline start, scope-label write grant)
  - id: charter
    resource: https://github.com/sipyourdrink-ltd/bernstein/blob/main/docs/governance/review-charter.md
    title: Review charter sections 1-3 and 6
  - id: pr5785
    resource: https://github.com/sipyourdrink-ltd/bernstein/pull/5785
    title: "ci(quorum): evaluate the review rules from the default branch"
  - id: pr5737
    resource: https://github.com/sipyourdrink-ltd/bernstein/pull/5737
    title: PR whose review API record shows the maintainer's burst-reply pattern
  - id: rulesets
    resource: "GitHub ruleset audit of 2026-09-09 and the maintainer's same-day confirmation; session record in pond (c31e4433)"
    title: Ruleset timeline (no durable public link)
---

# The stack, verified 2026-09-11 against the live repo

Five layers act on every pull request; only the last is a required check.

1. **Routing.** The CODEOWNERS `*` line requests all four core reviewers
   on everything; `area-steward-review.yml` runs on `pull_request_target`
   for `docs/**` and API-requests the docs steward, because stewards hold
   triage-not-write and GitHub ignores code owners without write.[^steward]
2. **Machine pre-review.** pr-labels, pr-policy, text hygiene, size
   labels, and queue hygiene (four rules, none reading review bodies).
3. **Bernstein reviews Bernstein.** The `deep-review` label triggers the
   repo's own root action (`uses: ./`) - claude CLI, a free-text review
   task, a $3.00 budget, findings posted as one PR comment. Two honesty
   rules: a fork PR (credential withheld) gets a *named* skip job so a
   green check never reads as reviewed-and-found-nothing, and a crashed
   review re-asserts failure. Fork PRs are never machine-deep-reviewed;
   "external contributions are reviewed by a maintainer by hand."[^prreview]
4. **Copilot**, primed by `.github/copilot-instructions.md`.
5. **Quorum.** `quorum.yml` is pinned by an organization ruleset as a
   required workflow (a branch cannot swap in its own copy) and always
   checks out `quorum_check.py`, the roster and CODEOWNERS from the
   DEFAULT branch, so a PR cannot promote its own author or unown a
   path.[^quorum][^pr5785] The script owns the charter arithmetic: two
   approvals with one core, approvals count only on the current head,
   `changes requested` survives pushes, a third approval over 400 lines
   or on `sandbox|security|audit` paths, over 1,000 lines split, a 72h
   hold on governance paths, automation self-merges on green except
   sensitive paths, and the maintainer merges with zero approvals while
   any standing committer veto blocks him.[^quorumscript][^charter]

**GitHub's native required-approvals rule is OFF** (dropped from
`2/true/true` to `0/false/false` on 2026-09-09 at 20:32; the second
ruleset only runs the merge queue). The review question is answered
entirely by the script since that date.[^rulesets][^pr5785]

# The maintainer's own reviewing is agent bursts

On the PR API his reviews appear as runs of zero-length `COMMENTED`
review shells one second apart wrapping batches of inline thread
replies - the artifact of posting comments individually through the API.
The replies are receipts, not opinions: fixes are applied and committed
first, then each thread is answered with the commit SHA ("Applied before
this round, in e4b88a001").[^pr5737] External reviewers batch similarly
(three approvals across three PRs inside 60 seconds has been observed).

# Why this matters to this repo

The `/review-pr` plan (docs/plans/2609-11-review-pr.md) targets exactly
the gap this stack leaves: nothing in it verifies what an executor
actually did - the quorum script checks who approved, the deep review is
advisory prose, and PR-body claims become permanent history unexecuted
(squash-merge). A review whose findings carry executable rubrics and
whose claims are re-run competes on the one axis upstream has not
covered. Operationally: expect review requests from the CODEOWNERS `*`
line on every PR, expect the fragment/hygiene bots to act before any
human, and read a `quorum` failure table as the charter speaking, not a
flaky check.

[^steward]: area-steward-review.yml
[^prreview]: bernstein-pr-review.yml
[^quorum]: quorum.yml
[^pr5785]: PR 5785
[^quorumscript]: quorum_check.py
[^charter]: Review charter sections 1-3 and 6
[^rulesets]: Ruleset timeline (no durable public link)
[^pr5737]: PR 5737 review API record

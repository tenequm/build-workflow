---
type: Reference
title: Contributing to upstream Bernstein - what its machinery actually enforces
description: The measured submission conventions of the upstream Bernstein repo - squash-merge makes the PR body the permanent commit message, fragments must close with the PR number, new tests must fail on base, prose is scanned by a hygiene denylist, and the bisect bot's regression labels are heuristic.
tags: [bernstein, upstream, contributing, ci, review]
status: stable
generated: { by: claude-code/fable-5, at: "2026-09-07T15:00:00Z" }
sources:
  - id: contributing
    resource: https://github.com/sipyourdrink-ltd/bernstein/blob/main/CONTRIBUTING.md
    title: Upstream CONTRIBUTING.md
  - id: governance
    resource: https://github.com/sipyourdrink-ltd/bernstein/blob/main/GOVERNANCE.md
    title: Upstream GOVERNANCE.md (no CLA, no sign-off)
  - id: pr5381
    resource: https://github.com/sipyourdrink-ltd/bernstein/pull/5381
    title: PR blocked once by its review bot, solely over the fragment's missing closing number
  - id: pr5378
    resource: https://github.com/sipyourdrink-ltd/bernstein/pull/5378
    title: PR whose review shows the bot reverting src/ and re-running the new tests
  - id: bisect
    resource: https://github.com/sipyourdrink-ltd/bernstein/pull/5381#issuecomment-5566818926
    title: bisect-on-red comment stating its own files-touched heuristic
  - id: pr5616
    resource: https://github.com/sipyourdrink-ltd/bernstein/pull/5616
    title: The TUI teardown fix that resolved that bisect label's actual cause
---

# How a change becomes history

Upstream squash-merges through a GitHub merge queue, and the squash replaces
the branch's commit bodies with the **PR description verbatim**, appending
`(#NNNN)` to the subject. Patch-id comparison of our merged PRs against our
branches showed the maintainers reshaped nothing - but every hand-written
commit body was discarded. Write the PR body as the permanent commit message;
never hand-append a PR number to the subject.[^pr5378]

# What blocks a PR

- **Release-notes fragment** under `docs/release-notes/fragments/`,
  `## <title>` plus prose, ending with `(#NNNN)` on its own line - the PR's
  own number, added after the PR exists. This is the one requirement the
  review bot has demonstrably blocked over.[^pr5381] Slug-only filenames are
  accepted for fixes without a tracking issue.
- **New tests must fail on base.** The bot's standard evidence step reverts
  `src/` to `origin/main` and re-runs the PR's tests; a test that passes both
  ways is called out.[^pr5378]
- **Prose hygiene.** A workflow scans the PR title, body, branch name, and
  every commit message against a private denylist whose documentation names
  em-dashes. Plain ASCII with single hyphens passes.[^contributing]
- No CLA and no `Signed-off-by` - do not add one.[^governance]

# Fork-PR quirks

The in-repo deep-review workflow withholds credentials on fork PRs (the
conductor App bot still comments), and `contract-drift-autofix` cannot push
to a fork so it fails red instead when anything under `src/bernstein/cli/`
drifts - the remedy is regenerating locally and committing the result.[^contributing]

# Reading their CI signals

`bisect-on-red` labels the highest-file-count commit since the last green
main run as the `regression` suspect and says itself that this is a
files-touched heuristic, not a bisect.[^bisect] Two properties make the label
weak evidence: main runs are frequently concurrency-cancelled (pushes land
every ~30 minutes with cancel-in-progress), so "the last green run" and "the
first completed run" are artifacts of cancellation timing; and a flaky test
surfacing under changed CI load will be attributed to whatever large commit
happens to sit in the window. Measured 2026-09-07: the label landed on a
tuning fix with zero code overlap with the failure, whose actual cause was a
latent TUI teardown race.[^bisect][^pr5616] Treat the label as a lead to
verify, never a verdict.

# Review culture

Small single-topic PRs with evidence-first bodies merge in days; maintainers
resolve drift on contributors' branches themselves rather than bouncing
them, and stale bot reviews are re-adjudicated against current main before
merge. The practical consequence: keep every PR one topic with its own
regression test, and put the reasoning for any early return or chosen
constant in the body - placement is expected to be argued.[^pr5381][^pr5378]

[^contributing]: Upstream CONTRIBUTING.md
[^governance]: Upstream GOVERNANCE.md
[^pr5381]: PR blocked once over the fragment's missing closing number
[^pr5378]: PR review showing the revert-and-rerun evidence step
[^bisect]: bisect-on-red comment stating its heuristic
[^pr5616]: The TUI teardown fix resolving that label's actual cause

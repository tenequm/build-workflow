# Knowledge Bundle Update Log

## 2026-09-08

* **Capture**: Added [automatic merge-back push behavior](findings/native-merge-back-pushes.md) and [merge evidence by execution path](findings/native-merge-evidence-varies-by-path.md), verified against native source and recording-executor integration tests. The operator adds a local-only prerequisite, admitted-ID resolution, exact merge-parent delivery proofs, and paired WAL closure.
* **Update**: Tightened the existing [phase-boundary decision](decisions/phase-boundary-between-engine-runs.md) with the shutdown-event ordering evidence; expanded [DONE-release and cache findings](findings/bernstein-done-releases-before-verification.md) with same-run population and fuzzy-key limitations; qualified [test-followup dispatch](findings/declared-but-unwired-engine-surfaces.md) with its branch guard and environment override; corrected [signal-delivery validation](findings/plan-post-drops-completion-signals.md) to distinguish readiness from stored-task checks. Added review dates for the upstream-dependent findings.
* **Capture**: Added [Phase ordering lives between engine runs](decisions/phase-boundary-between-engine-runs.md), [Bernstein releases dependents on worker-reported DONE](findings/bernstein-done-releases-before-verification.md), [A documented Bernstein surface is not a wired one](findings/declared-but-unwired-engine-surfaces.md), and [Plan-file completion signals are silently dropped at task POST](findings/plan-post-drops-completion-signals.md), from the bernstein_operator plan settlement (four adversarial review rounds, final verdict approve-with-nits).
* **Update**: Recorded the absorption outcome in [Bernstein is tracked upstream-first through a minimal rebased fork](decisions/upstream-first-minimal-fork.md) - all 11 upstream PRs merged, content diff showed nothing fork-only remaining, herdr suite green against a build of upstream main; the workflow now installs a source build of upstream main and the fork branch is retired.

## 2026-09-07

* **Capture**: Added [Codex turns can be silently truncated by its content filter](findings/codex-content-filter-truncates-executor-turns.md), from the same session's executor observations.
* **Capture**: Added [Bernstein is tracked upstream-first through a minimal rebased fork](decisions/upstream-first-minimal-fork.md), [Contributing to upstream Bernstein](references/contributing-to-bernstein.md), and [A fix proven in our environment is not proven for stock Bernstein](findings/validate-fixes-against-stock-assumptions.md), from the fork-reconciliation and upstream-submission session.
* **Initialization**: Created the bundle, seeded with [Workspace-at-first-write replaces the primary lock](decisions/workspace-at-first-write.md).

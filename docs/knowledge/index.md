---
okf_version: "0.2"
---

# What belongs here

Durable knowledge about the build-workflow project: decisions with their
rationale, findings with their evidence, rules with what they protect
against. Knowledge, not memory - current state (versions, in-flight work,
run results) stays in the ledger, git history, and release notes. AGENTS.md
keeps one-line laws; the rationale behind a law lives here, linked. Every
claim carries a source; a concept that stops being true is deprecated, never
deleted. Written as if this repository is public - because it is.

# Decisions

* [Workspace-at-first-write replaces the primary lock](decisions/workspace-at-first-write.md) - a build occupies only its workspace branch from the first artifact write; the 2026-09-03 repo-wide lock was dropped for it.
* [Bernstein is tracked upstream-first through a minimal rebased fork](decisions/upstream-first-minimal-fork.md) - the engine fork carries only fixes upstream does not yet have, rebuilt from upstream main whenever upstream absorbs some; every fix is submitted upstream as a small single-topic PR, and the fork dies once a PyPI release ships the last one.

# Findings

* [A fix proven in our environment is not proven for stock Bernstein](findings/validate-fixes-against-stock-assumptions.md) - pre-submission adversarial validation of three locally-proven engine fixes found one that would false-positive on every clean exit in stock target repos and disproved the premise of half of another.

# References

* [Contributing to upstream Bernstein - what its machinery actually enforces](references/contributing-to-bernstein.md) - squash-merge makes the PR body the permanent commit message, fragments must close with the PR number, new tests must fail on base, prose is scanned by a hygiene denylist, and the bisect bot's regression labels are heuristic.

# History

* [log.md](log.md) - bundle update history.

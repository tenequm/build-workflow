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

# History

* [log.md](log.md) - bundle update history.

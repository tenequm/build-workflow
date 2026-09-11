---
type: Decision
title: Session capture provisions a per-run pond store, with a pinned binary
description: Each review run creates a fresh pond store inside its workspace, ingests only its own session sources with scoped sync, requires every session receipt to resolve there, folds into the operator corpus best-effort, and exports a provenance.pond archive; the pond binary is version-pinned into the operator venv like the bernstein dep.
tags: [review-pr, pond, capture, provenance, pinning]
status: stable
generated: { by: claude-code/fable-5, at: "2026-09-11T12:00:00Z" }
sources:
  - id: probe
    resource: Empirical pond 0.17.2 probes on the operator sandbox, 2026-09-11
    title: Scoped sync into a fresh store, archive export, and the remote-store 403
  - id: loss
    resource: /findings/claude-acp-sessions-need-persistence-to-be-ingested.md
    title: The 6-of-12 silent capture loss that motivated verified capture
---

# Decision

Capture is a verified pipeline stage against a store the run owns, not a best-effort
sync into whatever the host has.

1. **A fresh store per run**, at `<workspace>/pond-store`, via `--storage-path`.
   In-run queries (session resolution, usage pricing) hit a store containing only
   this run's sessions, so the worktree-path join cannot collide with host noise and
   queries stay fast regardless of corpus size.
2. **Scoped ingest.** `pond sync <adapter> --path <dir>` per source directory the
   run's receipts imply - the munged Claude project dir per worktree, codex rollout
   day-directories, the agy conversations dir. Verified empirically: a fresh store
   ingests a single project directory in under a second with no adapter enablement
   or init step.[^probe]
3. **Verified resolution.** Every session receipt must resolve to a stored
   transcript; a miss is a named entry in the run summary, never silence. The
   6-of-12 loss this replaces was silent.[^loss]
4. **Fold, best-effort and recorded.** `pond copy --from <store> --to @` is pond's
   row-verified union merge (exit 6 on any missing row). It stays non-fatal because
   a box whose configured corpus is remote may hold read-only credentials - measured
   as a 403 on this sandbox[^probe] - and the host's own scheduled sync ingests the
   same sources regardless.
5. **The artifact.** `pond copy --from <store> --to provenance.pond` exports the run
   store as a compact restorable archive that travels with the run.
6. **The binary is pinned exactly**, like the bernstein engine revision:
   `just install-pond` provisions the pinned release (checksum-verified) into the
   operator venv, resolution prefers it over PATH, and readiness refuses a version
   ahead of the pin as firmly as one behind it - host pond drift must never change
   what a review does.

**Why:** capture that depends on host state fails silently and unreproducibly; a
store the run provisions is inspectable, exportable, and cheap to verify.

**How to apply:** anything new that reads or writes session data inside a run goes
through the run store; the host corpus is only ever a fold target. The pin lives in
`review_pr/pondsync.py` (PINNED) and `scripts/install-pond.sh`, updated together.

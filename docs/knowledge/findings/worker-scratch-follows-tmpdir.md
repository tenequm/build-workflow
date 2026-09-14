---
type: Finding
title: Worker scratch follows TMPDIR, so the corpus harness names it instead of inheriting it
description: A reviewing agent's own `mktemp -d` is charged to TMPDIR, and TMPDIR does reach a sandboxed worker - it is on bernstein's env passthrough allowlist and codex grants `$TMPDIR` as a writable root under workspace-write even outside the workspace. Inheriting it put worker scratch on whatever rootfs the host had, which capped eval concurrency at the small filesystem; the harness now sets it beside the workspace.
tags: [review-pr, corpus, disk, concurrency]
status: stable
generated: { by: claude-code/opus-5, at: "2026-09-14T19:30:00Z" }
sources:
  - id: allowlist
    resource: "bernstein 3.19.2, adapters/env_isolation.py - TMPDIR, TMP and TEMP in _BASE_ALLOWLIST, applied by build_filtered_env"
    title: "bernstein env isolation allowlist"
  - id: probe
    resource: "measured 2026-09-14 against codex-cli 0.154.0: `codex sandbox -c sandbox_mode=\"workspace-write\" -- bash -c 'mktemp -d'` with TMPDIR on /home created its directory there and wrote to it, both with TMPDIR inside the workdir and with TMPDIR entirely outside it"
    title: "codex sandbox TMPDIR probe"
  - id: guard
    resource: /fixtures/review-pr-cases/harness.py
    title: "harness.py - the pre-run disk guard"
---

# Finding

The eval harness refuses to start below `DISK_FLOOR_GB` free per concurrent case, and
it charges two filesystems: the workspace, and whatever `TMPDIR` names. The second is
not defensive duplication - a lens that copies the repository into its own `mktemp -d`
and builds there spends `TMPDIR`, which is where 6.3 GB of the pond#237 review went.

**`TMPDIR` does reach the worker**, by two independent mechanisms, both measured:
`TMPDIR`, `TMP` and `TEMP` sit in bernstein's env passthrough allowlist and are applied
by `build_filtered_env`,[^allowlist] and codex grants `$TMPDIR` as a writable root under
`workspace-write` - including when it points entirely outside the workspace.[^probe]

So the harness setting it is enough, and inheriting it was the defect. Left inherited,
worker scratch landed on the host's rootfs while the workspace sat on the big
filesystem, and the per-case floor was then governed by the smaller of the two: with a
10 GB floor and a 32 GB rootfs, three concurrent cases were refused on an otherwise
empty machine. The harness now creates `<work>/tmp`, exports it, and pins
`tempfile.tempdir` to match so its own checks read what its children read.

Two things this cost, worth recognising by shape rather than by detail:

- **Freeing the filesystem that is easy to see proves nothing about the one that
  binds.** Four `cargo clean`s took `/home` from 26 GB to 166 GB free and moved this
  blocker not at all, because `/home` was never the constraint. When a guard reads
  several resources, read which check failed, not which number improved.
- **A guard's comment outlived its evidence.** The harness asserted that a worker is
  handed a hardcoded `TMPDIR=/tmp` and never sees an exported one. The observation
  behind it was real - run 2's manager scratch did land in `/tmp` while an export was
  in force - but the explanation drawn from it was not tested, and it was then copied
  into three other files as settled fact. A measurement explains only what it measures.

Raising `DISK_FLOOR_GB` is not the lever and lowering it is forbidden: that floor exists
because run 1 of the pond#237 evaluation died when `/` reached 0.3 GB free and every
starved task quarantined permanently - see
[the quarantine finding](/docs/knowledge/findings/quarantine-makes-a-resource-outage-permanent.md).

[^allowlist]: bernstein env isolation allowlist
[^probe]: codex sandbox TMPDIR probe

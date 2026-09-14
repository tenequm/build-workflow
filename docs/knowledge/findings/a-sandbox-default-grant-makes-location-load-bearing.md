---
type: Finding
title: A sandbox's default grants make a checkout's location load-bearing, and two guards can pull against each other
description: Codex's workspace-write sandbox grants the worker's cwd plus a fixed list of system roots that includes /tmp but not the checkout root, so /review-pr's report write succeeded only by accident while workspaces lived under /tmp. Moving the checkout off /tmp to satisfy the disk guard silently removed that accident, and the second guard was written without noticing it depended on the first guard's violation.
tags: [review-pr, codex, sandbox, reliability]
status: stable
generated: { by: claude-code/opus-5, at: "2026-09-14T18:10:00Z" }
sources:
  - id: dlq
    resource: /docs/evals/2609-14-pond-237/run-2-undelivered/dlq.jsonl
    title: pond#237 run 2, the dead-letter queue showing four report-writer deaths
  - id: agent
    resource: /docs/evals/2609-14-pond-237/run-2-undelivered/report-writer-refusal.txt
    title: The report writer's own account of the read-only checkout
  - id: probe
    resource: "Measured directly with `codex sandbox`, codex-cli 0.154.0, on this host, 2026-09-14"
    title: Sandbox grant probes, positive and negative
  - id: skill
    resource: /skills/review-pr/SKILL.md
    title: The invocation, its shim and its probe
---

# Finding

**`--sandbox workspace-write` grants the worker's own cwd and a fixed list of
system roots. `/tmp` is on that list. The checkout root is not.**[^probe] The
/review-pr goal text requires `review-report.md` at the checkout root, and a
codex worker runs from a worktree nested under it, so the write it is
instructed to make is outside its writable set - unless the checkout happens to
sit under `/tmp`, where a default grant covers it.

Every corpus case lives under `/tmp`. Every corpus report therefore landed, and
the delivery step was never actually exercised. The skill passed its own
regression suite on an accident.

## The two guards pulled against each other

Run 1 of pond#237 died because `/tmp` filled. The fix moved the checkout to a
big filesystem and added a guard refusing a lane below a disk floor. That fix
was correct and it removed the accidental grant in the same motion: all nine
lenses finished, and every report writer died reporting the checkout "mounted
read-only".[^agent] It refused to fake success, which is the behavior we want,
and bernstein then retried it three more times at up to 1.95M input tokens an
attempt.[^dlq]

**The general lesson: a guard can depend on a condition that another guard
exists to destroy.** The disk guard's whole purpose is to move files off `/tmp`;
the delivery path's unstated precondition was that they be on `/tmp`. Neither is
visible from the other, and the corpus could not see either, because the corpus
satisfied the hidden precondition on every run. What surfaced it was a failure
in production shape - a real repository, on a real filesystem, outside the one
directory the suite ever used.

This is the same shape as
[TMPDIR never reaching a worker](quarantine-makes-a-resource-outage-permanent.md):
a setting that appears to control a child process, and a boundary in between
that quietly decides otherwise. The difference is the direction of the error.
There, an export looked like a control and was inert. Here, a grant nobody
configured was doing load-bearing work, so removing it broke something no one
had connected to it.

## What closes it

Prose cannot, because the failure happens before any model reads anything.
Both halves are checks:

- The shim grants the checkout root through
  `sandbox_workspace_write.writable_roots`. Unlike the reasoning-effort value
  beside it, this one IS interpolated, because the path is per-run.
- A probe refuses the lane before any model spawns, in the invocation and in the
  harness alike. It costs no model call - `codex sandbox` runs a shell command
  under the policy with nothing attached - and it checks both failure modes: a
  shim that does not carry the grant, and a grant that does not work here.

Two details are load-bearing and were measured, not assumed:[^probe]

- **The probe must run from a subdirectory of the checkout.** From the root,
  `workspace-write` grants the cwd and the check passes vacuously - confirmed by
  running it both ways.
- **`codex sandbox` honours `-c` only after the subcommand; `codex exec` honours
  it in the shim's position ahead of it.** The same override placed before
  `sandbox` is silently ignored. A probe written to mirror the shim's argv order
  would have reported a denial that the real lane does not have.

[^dlq]: pond#237 run 2 dead-letter queue: two `max_retries_exceeded` entries for "Write the review report", each `Agent report-writer-... died; janitor failed: ['path_exists: .../review-report.md (not found)']`; four report-writer sessions in all, one of them consuming 1,949,221 input tokens.
[^agent]: report-writer-b998008a, final message: "Blocked by filesystem permissions: `/home/tenequm/review-pond-237/src` is mounted read-only. Both patching and direct creation of `review-report.md` were rejected. No files were modified, and I did not commit, push, or mark the task complete."
[^probe]: `codex sandbox -c sandbox_mode="workspace-write"`, cwd a subdirectory: write to the parent under `/home` DENIED ("Read-only file system"), the identical write under `/tmp` ALLOWED, and under `/home` with `writable_roots` naming the parent ALLOWED. A mistyped key (`writeable_roots`) fails closed, denied. From the checkout root with no grant, ALLOWED - the vacuity case. `codex exec` with the override in the shim's position ahead of the subcommand ALLOWED; `codex sandbox` with it in that position DENIED.

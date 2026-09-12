---
type: Finding
title: A driver's exit is not a bernstein run's end - orphaned orchestrators keep working
description: bernstein orchestrators start in their own session (start_new_session), so when the launching driver dies the orchestrator reparents to systemd --user and keeps spawning workers and burning tokens into a workdir nothing reads - observed 40+ minutes after driver death, and the final worker generation then outlives the orchestrator too; ending a run means killing the orchestrator and sweeping its workers, not just the driver.
tags: [bernstein, eval, review-pr, operations]
status: stable
stale_after: "2027-03-11T00:00:00Z"
generated: { by: claude-code/fable-5, at: "2026-09-11T23:15:00Z" }
sources:
  - id: census
    resource: "process census of 2026-09-11 21:29 UTC on this host (cross-session audit): 9 dead eval runs had left 38 bernstein processes / 5.1GB RSS reparented to systemd --user; run 205249Z was still spawning reviewer/qa/security agents 36 minutes after its driver died"
    title: the leak, measured
  - id: sweep
    resource: "cleanup of 2026-09-11 ~22:00 UTC: killing the orphaned orchestrators left their last worker generation (15 pi agents in .sdd/worktrees) alive and working; a /proc cwd scan found them, a second kill pass cleared them, and deleting the dead workdirs freed 19GB (rootfs 89% to 30%)"
    title: the two-generation sweep
  - id: spawn
    resource: bernstein 3.19.1 adapters/pi.py (subprocess.Popen with start_new_session=True), harness timeout via subprocess.run which kills only the direct child
    title: why nothing dies together
  - id: waitonly
    resource: bernstein as installed, cli/run_bootstrap.py:2131-2144 (--wait help) and :1480-1506 (_wait_for_run_completion, "A None return means no verdict: the deadline expired")
    title: --wait bounds the CLI waiter, never the orchestrator
  - id: receipt
    resource: "harness.log of /tmp/review-eval-20260911T221816Z/floor/case-02, the first case run after the sweep was added: `sweep: {'found': 9, 'exited': 8, 'killed': 1, 'survived': 0}`, written when the CLI returned at its timeout while nine processes were still working in the case tree"
    title: the sweep's receipt, from the first run that carried it
---

# Finding

bernstein spawns workers with `start_new_session=True` and the orchestrator
itself detaches from the CLI that launched it, so killing or timing out the
driver (`just eval`, `harness.py`, a Ctrl-C'd `bernstein run`) ends nothing:
the orchestrator reparents to `systemd --user` and keeps scheduling agents
into a workdir with no reader.[^census]

The leak is two generations deep. Killing an orphaned orchestrator does not
reap its in-flight workers - they are session leaders of their own - so a
sweep must find them separately; scanning `/proc/*/cwd` for the run's
workdir is the reliable census, since every worker chdirs into a
`.sdd/worktrees/<role>-<id>` under it.[^sweep][^spawn]

`--wait` does not help. It bounds the CLI waiter and nothing else: its own
help calls it a ceiling on blocking, and the waiter returns "no verdict" when
the deadline expires while the orchestrator carries on.[^waitonly] A harness
comment that calls `--wait` "the orchestrator's own in-run ceiling" is
describing something the engine does not do, which matters because it makes an
explicit sweep look optional when it is the only guard there is.

The sweep leaves a receipt, and the receipt is what makes it auditable. The first
run launched after the guard existed recorded `sweep: {'found': 9, 'exited': 8,
'killed': 1, 'survived': 0}` in its `harness.log` - nine processes still working
inside a case whose CLI had already returned, one of which ignored SIGTERM and
needed SIGKILL.[^receipt] Earlier runs carry no such line for the mundane reason
that they were launched before the guard was written, which is why an orphan
guard without observable output cannot be told apart from one that never ran.

Operationally: to end a run early, kill the orchestrator, then cwd-scan for
its workers and kill those, then delete the workdir. Verifying a run is
dead by its driver's exit code alone leaves it billing quietly - nine dead
runs accumulated 38 processes, 5.1GB RSS and 19GB of disk in one day.[^census][^sweep]

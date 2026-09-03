"""Process discovery shared by the CLI (run-config refusal) and the watcher."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def stale_bernstein_pids(root: Path, cwd_memo: dict[tuple[int, str], bool] | None = None) -> list[tuple[int, str]]:
    """Live `bernstein` processes belonging to this repo, by argv or by cwd.

    A killed run does not take its orchestrator and watchdog with it. They keep ticking
    against `.sdd/` under the same root and respawn tasks into the NEXT run's
    directories -- the 2026-09-02 replay lost a whole run to two orphans from the
    previous one. The port refusal only sees the task server, which is a different
    process and may already be gone, so match on the repo instead: the root in the argv,
    or the root (or a path under it) as the process cwd.

    `cwd_memo` caches the lsof cwd verdict per (pid, argv): a process's cwd does not
    change, and the watcher calls this every tick for hours -- unmemoised that is one
    ~70ms lsof per engine process per tick (measured 2026-09-04).
    """
    listing = subprocess.run(["pgrep", "-fl", "bernstein"], capture_output=True, text=True, check=False).stdout
    hits: list[tuple[int, str]] = []
    for line in listing.splitlines():
        pid_s, _, cmd = line.partition(" ")
        if not pid_s.isdigit() or int(pid_s) == os.getpid():
            continue
        pid = int(pid_s)
        if str(root) in cmd:
            hits.append((pid, cmd[:120]))
            continue
        key = (pid, cmd)
        owned = cwd_memo.get(key) if cwd_memo is not None else None
        if owned is None:
            owned = False
            cwd = subprocess.run(["lsof", "-p", str(pid), "-a", "-d", "cwd", "-Fn"], capture_output=True, text=True, check=False).stdout
            for l in cwd.splitlines():
                if l.startswith("n") and (l[1:] == str(root) or l[1:].startswith(f"{root}/")):
                    owned = True
                    break
            if cwd_memo is not None:
                cwd_memo[key] = owned
        if owned:
            hits.append((pid, cmd[:120]))
    return hits

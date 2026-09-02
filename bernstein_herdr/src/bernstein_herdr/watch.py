"""Settle watcher: exit 0 when the report file exists and the agent has been idle twice, 20 s apart.

Usage: python -m bernstein_herdr.watch <agent-name> <report-path> <log-path> [--archive <base-sha>]
With --archive, also write diff.patch, numstat.txt and status.txt next to the report (shadow lane).
"""

from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

IDLE_STATES = {"idle", "done"}


def status(name: str) -> str:
    out = subprocess.run(["herdr", "agent", "get", name], capture_output=True, text=True, check=False).stdout
    for token in ("idle", "done", "working", "blocked", "unknown"):
        if f'"agent_status":"{token}"' in out:
            return token
    return "gone"


def main() -> int:
    name, report, log = sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3])
    archive_base = sys.argv[sys.argv.index("--archive") + 1] if "--archive" in sys.argv else None
    idle = 0
    while True:
        st = status(name)
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text(f"{time.strftime('%FT%TZ', time.gmtime())} {st} report={'yes' if report.exists() else 'no'}\n")
        if st == "blocked":
            return 2
        if st == "gone" and not report.exists():
            return 1
        if report.exists() and st in IDLE_STATES:
            idle += 1
            if idle >= 2:
                break
        else:
            idle = 0
        time.sleep(20)
    if archive_base:
        wt = report.parent.parent if report.parent.name == ".agents" else Path.cwd()
        run = lambda *a: subprocess.run(a, cwd=wt, capture_output=True, text=True, check=False).stdout
        run("git", "add", "-A", "-N", ".")
        (wt / "diff.patch").write_text(run("git", "diff", archive_base, "--", ".", ":!.agents"))
        (wt / "numstat.txt").write_text(run("git", "diff", archive_base, "--numstat", "--", ".", ":!.agents"))
        (wt / "status.txt").write_text(run("git", "status", "--porcelain"))
        run("git", "reset", "-q")
    return 0


if __name__ == "__main__":
    sys.exit(main())

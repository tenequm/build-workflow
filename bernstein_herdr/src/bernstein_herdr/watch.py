"""Settle watcher for one executor pane.

Exit 0 once the report file exists and the agent has read idle twice, 20 s apart;
exit 2 on a blocked agent; exit 1 if the agent vanished without a report.
On settle: copy the report into <run>/reports/<step>.md (or <run>/shadow/<step>/),
archive diff/numstat/status, append a runs.jsonl row, close the tab for shadow lanes.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import time
from pathlib import Path

from bernstein_herdr import herdr, ledger

IDLE = {"idle", "done"}


def main() -> int:
    ap = argparse.ArgumentParser()
    for k in ("agent", "worktree", "report", "run_dir", "step", "base", "kind", "model", "started", "lane"):
        ap.add_argument(f"--{k.replace('_', '-')}", required=True)
    a = ap.parse_args()
    wt, run_dir = Path(a.worktree), Path(a.run_dir)
    report = wt / a.report
    idle = 0
    blocks = 0
    while True:
        st = herdr.status(a.agent)
        print(f"{ledger.now()} {st} report={'yes' if report.exists() else 'no'}", flush=True)
        if st == "blocked":
            blocks += 1
            ledger.note(run_dir, f"blocked step={a.step} lane={a.lane} agent={a.agent}")
            return 2
        if st == "gone" and not report.exists():
            ledger.note(run_dir, f"agent gone without report step={a.step} lane={a.lane}")
            return 1
        idle = idle + 1 if (report.exists() and st in IDLE) else 0
        if idle >= 2:
            break
        time.sleep(20)
    wall = int(time.time() - float(a.started))
    dest = run_dir / ("shadow" if a.lane == "shadow" else "reports") / a.step
    stats = ledger.archive(wt, a.base, dest)
    if report.exists():
        shutil.copy(report, dest / "report.md")
    claims = ledger.report_claims(report)
    ledger.row(run_dir, {
        "run_id": f"{run_dir.name}-{a.step}-{a.lane}-{a.kind}", "step": a.step, "lane": a.lane, "base": a.base,
        "arm": {"agent": a.kind, "model": a.model}, "wall_s": wall, "blocks": blocks, "diff": stats,
        "report": claims, "worktree": str(wt), "evidence": "reported",
    })
    ledger.note(run_dir, f"settled step={a.step} lane={a.lane} wall_s={wall} files={stats['files']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

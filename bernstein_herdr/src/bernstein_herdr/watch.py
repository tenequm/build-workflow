"""Event watcher for a live run: replaces the driver's manual polling loop.

`bernstein-herdr watch` blocks, printing ONE line per event, and exits when the
run is over (no Bernstein process owns this root and no activity arrives for a
grace period). Run it in the background and read its output on completion or on
a stall line; the seven-command 30-60s manual poll in build-run step 5 is what
this replaces.

Events, one line each, `<HH:MM:SS> <TAG> <detail>`:
  ROW      a new runs.jsonl attempt row (the tail of the row)
  SPAWNER  a spawner.log line matching the known trouble patterns
  LEDGER   a new ledger.md line
  STALL    no activity for --stall minutes while a Bernstein process is alive
           (apply build-run's stall rule: check the agent log mtime, kill if stale)
  END      no Bernstein process owns this root and the grace period passed

Exit code: 0 on END, 3 on --until-stall with a STALL seen.
"""

from __future__ import annotations

import re
import time
from datetime import datetime
from pathlib import Path

TROUBLE = re.compile(r"liveness_judgment|SIGTERM|Timeout after|Refusing to merge|409|ownership conflict|retry_or_fail_task|permanent_fail|max_retries_exceeded")


def _say(tag: str, detail: str) -> None:
    print(f"{datetime.now().strftime('%H:%M:%S')} {tag:8} {detail[:400]}", flush=True)


class _Tail:
    def __init__(self, path: Path):
        self.path = path
        self.pos = path.stat().st_size if path.exists() else 0

    def new_lines(self) -> list[str]:
        if not self.path.exists():
            return []
        size = self.path.stat().st_size
        if size < self.pos:  # rotated or truncated
            self.pos = 0
        if size == self.pos:
            return []
        with self.path.open("r", errors="replace") as f:
            f.seek(self.pos)
            chunk = f.read()
            self.pos = f.tell()
        return [l for l in chunk.splitlines() if l.strip()]


def watch(root: Path, run_dir: Path, interval: float = 10.0, stall_minutes: float = 25.0,
          end_grace: float = 60.0, until_stall: bool = False) -> int:
    from bernstein_herdr.cli import stale_bernstein_pids

    tails = {"ROW": _Tail(run_dir / "runs.jsonl"),
             "LEDGER": _Tail(run_dir / "ledger.md"),
             "SPAWNER": _Tail(root / ".sdd" / "runtime" / "spawner.log")}
    last_activity = time.monotonic()
    dead_since: float | None = None
    stalled = False
    _say("WATCH", f"root={root} run={run_dir} interval={interval}s stall={stall_minutes}m")
    while True:
        active = False
        for tag, tail in tails.items():
            for line in tail.new_lines():
                if tag == "SPAWNER" and not TROUBLE.search(line):
                    continue
                _say(tag, line)
                active = True
        if active:
            last_activity = time.monotonic()
            stalled = False
        alive = bool(stale_bernstein_pids(root))
        if alive:
            dead_since = None
            idle = time.monotonic() - last_activity
            if idle > stall_minutes * 60 and not stalled:
                stalled = True
                _say("STALL", f"no run activity for {idle/60:.0f}m with a live bernstein process; "
                              f"check the newest agent log mtime under .sdd/ and kill the session if stale")
                if until_stall:
                    return 3
        else:
            dead_since = dead_since or time.monotonic()
            if time.monotonic() - dead_since > end_grace:
                _say("END", "no bernstein process owns this root; run is over")
                return 0
        time.sleep(interval)

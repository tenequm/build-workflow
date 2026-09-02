"""`bernstein-herdr` CLI: run a gate from a plan's completion_signals, or decode an agy session.

  bernstein-herdr scorer --step <name>       runs ScorerGate in the current worktree, exit 0/1
  bernstein-herdr blind-judge --step <name>  runs BlindJudgeGate, exit 0/1
  bernstein-herdr agy-session <db> [name]    per-turn timing and token totals from an agy conversation DB
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _changed_files(base: str) -> list[str]:
    out = subprocess.run(["git", "diff", "--name-only", base], capture_output=True, text=True, check=False).stdout
    return [l for l in out.splitlines() if l]


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    cmd = sys.argv[1]
    if cmd == "agy-session":
        from bernstein_herdr.agy_session import main as agy_main
        return agy_main(sys.argv[2:])
    import os
    base = os.environ.get("BUILD_BASE_REF", "HEAD~1")
    step = sys.argv[sys.argv.index("--step") + 1] if "--step" in sys.argv else "step"
    if cmd == "scorer":
        from bernstein_herdr.gates.scorer import ScorerGate
        gate = ScorerGate()
    elif cmd == "blind-judge":
        from bernstein_herdr.gates.blind_judge import BlindJudgeGate
        gate = BlindJudgeGate()
    else:
        print(__doc__)
        return 2
    res = gate.run(_changed_files(base), Path.cwd(), step, "")
    print(res.details)
    return 0 if res.status == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())

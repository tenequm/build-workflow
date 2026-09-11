"""ACP stdio bridge: pin Claude SDK options acpx does not expose as flags.

Only session/new is changed. Responses, tool calls and cancellation pass through
unchanged. Each ceremony uses acpx exec, so no prior session can be resumed.
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys


def bind_session(message: dict, *, budget: float, model: str, turns: int) -> dict:
    if message.get("method") in {"session/load", "session/resume", "session/fork"}:
        raise ValueError("blind judge cannot load, resume, or fork a session")
    if message.get("method") != "session/new":
        return message
    params = message.setdefault("params", {})
    meta = params.setdefault("_meta", {})
    options = meta.setdefault("claudeCode", {}).setdefault("options", {})
    options.update(
        {
            "maxBudgetUsd": budget,
            "model": model,
            "maxTurns": turns,
            "settingSources": [],
            "persistSession": False,
            "tools": ["Read", "Glob", "Grep", "Bash", "Write", "Edit"],
            "mcpServers": {},
        }
    )
    params["mcpServers"] = []
    return message


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budget", type=float, required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--turns", type=int, required=True)
    parser.add_argument("adapter", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    argv = args.adapter[1:] if args.adapter[:1] == ["--"] else args.adapter
    if not argv or not math.isfinite(args.budget) or args.budget <= 0 or args.turns <= 0:
        parser.error("adapter argv, positive finite budget, and positive turns required")
    # Inherit the enclosing process group. The driver's wrapper owns final reaping.
    process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=sys.stdout.buffer)
    pipe = process.stdin
    assert pipe is not None  # Popen was explicitly configured with stdin=PIPE.
    try:
        for line in sys.stdin.buffer:
            message = bind_session(
                json.loads(line), budget=args.budget, model=args.model, turns=args.turns
            )
            pipe.write((json.dumps(message, separators=(",", ":")) + "\n").encode())
            pipe.flush()
    finally:
        pipe.close()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=10)
    raise SystemExit(process.returncode)


if __name__ == "__main__":
    main()

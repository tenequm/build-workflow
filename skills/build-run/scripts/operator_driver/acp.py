"""One-shot Claude ACP command and validated protocol evidence."""

from __future__ import annotations

import json
import math
import shlex
import sys
from pathlib import Path

from .storage import Park


def judge_argv(spec: dict, worktree: Path, prompt: Path) -> list[str]:
    bridge = [
        sys.executable,
        "-m",
        "operator_driver.claude_acp",
        "--budget",
        str(spec["budget_usd"]),
        "--model",
        spec["model"],
        "--turns",
        str(spec["max_turns"]),
        "--",
        *spec["adapter_argv"],
    ]
    return [
        "acpx",
        "--cwd",
        str(worktree),
        "--format",
        "json",
        "--json-strict",
        "--timeout",
        str(spec["timeout_s"]),
        "--prompt-retries",
        "0",
        "--approve-all",
        "--non-interactive-permissions",
        "fail",
        "--agent",
        shlex.join(bridge),
        "exec",
        "--file",
        str(prompt),
    ]


def transcript(log: bytes, *, complete: bool = True) -> dict:
    """Read cumulative session cost, never sum repeated usage notifications."""
    sessions = set()
    cost = None
    stop = None
    errors = []
    lines = log.splitlines(keepends=True)
    for line in lines:
        if not line.endswith(b"\n"):
            if not complete:
                break
            raise Park("truncated ACP transcript")
        try:
            message = json.loads(line)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise Park("non-JSON ACP transcript") from exc
        if not isinstance(message, dict):
            raise Park("invalid ACP message")
        if "error" in message:
            errors.append(message["error"])
        result = message.get("result", {})
        if isinstance(result, dict) and "stopReason" in result:
            if stop is not None:
                raise Park("multiple ACP prompt results in one blind ceremony")
            stop = result["stopReason"]
        if message.get("method") != "session/update":
            continue
        params = message.get("params", {})
        session = params.get("sessionId")
        if not isinstance(session, str) or not session:
            raise Park("ACP update has no session identity")
        sessions.add(session)
        if len(sessions) > 1:
            raise Park("multiple ACP sessions in one blind ceremony")
        update = params.get("update", {})
        if update.get("sessionUpdate") != "usage_update" or update.get("cost") is None:
            continue
        reported = update["cost"]
        amount = reported.get("amount") if isinstance(reported, dict) else None
        if (
            not isinstance(reported, dict)
            or reported.get("currency") != "USD"
            or isinstance(amount, bool)
            or not isinstance(amount, (int, float))
            or not math.isfinite(amount)
            or amount < 0
        ):
            raise Park("invalid ACP USD cost evidence")
        if cost is not None and amount < cost:
            raise Park("ACP cumulative cost moved backwards")
        cost = float(amount)
    if complete and (cost is None or len(sessions) != 1):
        raise Park("judge has no measured ACP cost; spend remains unresolved")
    return {
        "cost_usd": cost,
        "session_id": next(iter(sessions), None),
        "stop_reason": stop,
        "errors": errors,
    }

"""One-shot ACP judge command and validated protocol evidence.

transport `claude` (default) wraps the adapter in the Claude session bridge, which
binds budget, model and turn limits and reports cumulative USD cost. transport `acp`
runs any other ACP agent (e.g. Antigravity) with the model passed to acpx; such
subscription-backed agents report no cost, so their ceremonies are unmetered.
"""

from __future__ import annotations

import json
import math
import shlex
import sys
from pathlib import Path

from .storage import Park, atomic


def claude_bridge(spec: dict) -> bool:
    """Whether this ceremony runs through the Claude session bridge, which is also
    the only transport whose adapter reports a cumulative USD cost."""
    return spec.get("transport", "claude") == "claude"


def judge_argv(spec: dict, worktree: Path, prompt: Path) -> list[str]:
    # acpx otherwise resolves MCP servers from the reviewed tree itself (.acpxrc.json)
    # and then the home config, so a repository under blind review could hand servers
    # to its own reviewer. An empty set is passed on every transport; acpx wants a
    # JSON array here, not the object map other tools use.
    empty_mcp = prompt.with_name("mcp-none.json")
    atomic(empty_mcp, b'{"mcpServers": []}\n')
    mcp = ["--mcp-config", str(empty_mcp)]
    if claude_bridge(spec):
        agent = [
            sys.executable,
            "-m",
            "operator_driver.claude_acp",
            "--budget",
            str(spec["budget_usd"]),
            "--model",
            spec["model"],
            "--turns",
            str(spec["max_turns"]),
            # A judge never persists; a caller that needs the transcript ingested later
            # asks for it explicitly.
            *(["--persist"] if spec.get("persist_session") else []),
            "--",
            *spec["adapter_argv"],
        ]
        bounds = mcp
    else:
        # The bridge's Claude session options cannot reach another agent, so the model,
        # turn ceiling and tool set are asked for through acpx instead. Only the empty
        # MCP set and the ceremony's own timeout bind an agent that ignores acpx's
        # Claude-shaped session metadata; turns and tools are a request it may refuse,
        # which is why an unmetered transport still settles at its full reservation.
        agent = spec["adapter_argv"]
        bounds = [
            "--model",
            spec["model"],
            "--max-turns",
            str(spec["max_turns"]),
            "--allowed-tools",
            "Read,Glob,Grep,Bash,Write,Edit",
            *mcp,
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
        *bounds,
        "--agent",
        shlex.join(agent),
        "exec",
        "--file",
        str(prompt),
    ]


def transcript(log: bytes, *, complete: bool = True, require_cost: bool = True) -> dict:
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
    if complete and len(sessions) != 1:
        raise Park("judge transcript has no ACP session")
    if complete and require_cost and cost is None:
        raise Park("judge has no measured ACP cost; spend remains unresolved")
    return {
        "cost_usd": cost,
        "session_id": next(iter(sessions), None),
        "stop_reason": stop,
        "errors": errors,
    }

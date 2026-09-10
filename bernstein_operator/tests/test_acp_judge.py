from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from operator_driver.acp import judge_argv, transcript
from operator_driver.claude_acp import bind_session
from operator_driver.storage import Park


def event(cost=None, session="fresh"):
    update = {"sessionUpdate": "usage_update", "used": 100, "size": 1000}
    if cost is not None:
        update["cost"] = {"amount": cost, "currency": "USD"}
    return {
        "jsonrpc": "2.0",
        "method": "session/update",
        "params": {"sessionId": session, "update": update},
    }


def stream(*messages):
    return b"".join(json.dumps(message).encode() + b"\n" for message in messages)


def test_cost_is_cumulative_and_bound_to_one_session():
    result = transcript(
        stream(event(0.1), event(), event(0.2), {"id": 3, "result": {"stopReason": "end_turn"}})
    )
    assert result["cost_usd"] == 0.2
    assert result["stop_reason"] == "end_turn"
    with pytest.raises(Park, match="multiple ACP sessions"):
        transcript(stream(event(0.1), event(0.2, "other")))
    with pytest.raises(Park, match="backwards"):
        transcript(stream(event(0.2), event(0.1)))


@pytest.mark.parametrize("amount", [True, -1, float("nan"), float("inf"), "0.1"])
def test_invalid_cost_never_counts_as_zero(amount):
    with pytest.raises(Park, match="invalid ACP USD"):
        transcript(stream(event(amount)))


def test_missing_cost_and_incomplete_protocol_do_not_pass():
    with pytest.raises(Park, match="measured ACP cost"):
        transcript(stream(event()))
    with pytest.raises(Park, match="truncated"):
        transcript(stream(event(0))[:-1])
    assert transcript(stream(event(0.1)) + b'{"partial', complete=False)["cost_usd"] == 0.1


def test_unmetered_transport_accepts_absent_cost_but_not_a_missing_session():
    assert transcript(stream(event()), require_cost=False)["cost_usd"] is None
    assert transcript(stream(event(0.3)), require_cost=False)["cost_usd"] == 0.3
    with pytest.raises(Park, match="no ACP session"):
        transcript(stream({"id": 1, "result": {"stopReason": "end_turn"}}), require_cost=False)


def test_acp_transport_keeps_its_bounds_without_the_claude_bridge(tmp_path):
    """The bridge's session metadata cannot reach another agent, so acpx's own flags
    carry the turn ceiling, the review tool set and an empty MCP surface."""
    spec = {"transport": "acp", "model": "gemini-3.7-flash-low", "timeout_s": 5, "max_turns": 9}
    prompt = tmp_path / "prompt.md"
    argv = judge_argv({**spec, "adapter_argv": ["/bin/agy-acp", "--uid="]}, tmp_path, prompt)
    assert argv[argv.index("--model") + 1] == "gemini-3.7-flash-low"
    assert argv[argv.index("--max-turns") + 1] == "9"
    assert "Agent" not in argv[argv.index("--allowed-tools") + 1]
    assert json.loads(Path(argv[argv.index("--mcp-config") + 1]).read_text()) == {"mcpServers": []}
    assert argv[argv.index("--agent") + 1] == "/bin/agy-acp --uid="
    assert "operator_driver.claude_acp" not in " ".join(argv)


def test_bridge_pins_budget_and_settings_and_forbids_resume():
    message = {
        "method": "session/new",
        "params": {
            "mcpServers": [{"name": "ambient"}],
            "_meta": {"claudeCode": {"options": {"maxBudgetUsd": 100, "settingSources": ["user"]}}},
        },
    }
    bound = bind_session(message, budget=1.5, model="pinned-model", turns=4)
    options = bound["params"]["_meta"]["claudeCode"]["options"]
    assert options["maxBudgetUsd"] == 1.5
    assert options["maxTurns"] == 4
    assert options["settingSources"] == []
    assert options["persistSession"] is False
    assert "Agent" not in options["tools"]
    assert bound["params"]["mcpServers"] == []
    with pytest.raises(ValueError, match="blind judge"):
        bind_session({"method": "session/load"}, budget=1, model="x", turns=1)


@pytest.mark.skipif(shutil.which("acpx") is None, reason="acpx executable unavailable")
def test_real_acpx_one_shot_against_recording_acp_server(tmp_path):
    """Real transport, no model invocation or provider spend."""
    adapter = tmp_path / "recording_adapter.py"
    adapter.write_text("""import json, sys
from pathlib import Path
for line in sys.stdin:
    request = json.loads(line)
    method = request.get("method")
    if method == "initialize":
        result = {"protocolVersion": 1, "agentCapabilities": {}, "authMethods": []}
    elif method == "session/new":
        Path("session-options.json").write_text(json.dumps(request["params"]))
        result = {"sessionId": "fresh-session"}
    elif method == "session/prompt":
        print(json.dumps({"jsonrpc": "2.0", "method": "session/update", "params": {
            "sessionId": "fresh-session", "update": {"sessionUpdate": "usage_update",
            "used": 10, "size": 1000, "cost": {"amount": 0.125, "currency": "USD"}}}}), flush=True)
        result = {"stopReason": "end_turn"}
    else:
        result = {}
    if "id" in request:
        print(json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": result}), flush=True)
""")
    prompt = tmp_path / "prompt.md"
    prompt.write_text("Review the frozen input.")
    spec = {
        "budget_usd": 2,
        "timeout_s": 20,
        "model": "pinned-model",
        "max_turns": 4,
        "adapter_argv": [sys.executable, str(adapter)],
    }
    scripts = str(Path(__file__).resolve().parents[2] / "skills/build-run/scripts")
    env = {**os.environ, "PYTHONPATH": scripts + os.pathsep + os.environ.get("PYTHONPATH", "")}
    result = subprocess.run(
        judge_argv(spec, tmp_path, prompt), env=env, cwd=tmp_path, capture_output=True, timeout=30
    )
    assert result.returncode == 0, result.stderr.decode()
    assert transcript(result.stdout)["cost_usd"] == 0.125
    options = json.loads((tmp_path / "session-options.json").read_text())
    assert options["_meta"]["claudeCode"]["options"]["maxBudgetUsd"] == 2

#!/usr/bin/env python3
"""A recording ACP agent: the real transport, canned judgment, no provider spend.

acpx, the session bridge, `launch_once`, the worktree allowlist check, the
report-witness law and the ACP cost evidence are all exercised for real. The only
thing replaced is the part that costs money and cannot be replayed - what the model
decides. The canned decisions come from the policy file named by
`REVIEW_PR_RECORDING`; the agent works out which report it owes from the brief it is
handed, exactly as a real reviewer would.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

REPORT = re.compile(r"Write exactly one file and no others: `([^`]+)`")
FINDING = re.compile(r'"verification" field reads `([^`]+)`')
CLAIM = re.compile(r"## The claim.*?\n\n(.+?)\n\nEvidence offered", re.DOTALL)


def operation() -> str:
    """The driver gives every session its own worktree, named for the operation.

    That is what lets one recorded agent answer as a different family per run without
    the brief having to name the family - which it must not, for a verifier.
    """
    return Path.cwd().parent.name


# acpx applies `--model` to a non-Claude agent only when the agent advertises its
# models; a real codex or Antigravity server does, so the recording one must too, or
# the acp transport is never exercised at all.
DEFAULT_MODELS = (
    "gpt-5.6-sol",
    "gpt-5.6-terra",
    "gemini-3.7-flash-medium",
    "gemini-3.8-flash-high",
    "claude-opus-5",
    "claude-sonnet-5",
    "claude-haiku-4-5-20251001",
)


def policy() -> dict:
    """From argv first: a review session inherits only a credential allowlist, so an
    environment variable set by whoever launched the review never reaches here."""
    path = None
    argv = sys.argv[1:]
    if "--policy" in argv:
        path = argv[argv.index("--policy") + 1]
    path = path or os.environ.get("REVIEW_PR_RECORDING")
    if not path or not Path(path).is_file():
        return {}
    return json.loads(Path(path).read_text())


def prompt_text(params: dict) -> str:
    chunks = []
    for block in params.get("prompt") or []:
        if isinstance(block, dict) and isinstance(block.get("text"), str):
            chunks.append(block["text"])
        elif isinstance(block, str):
            chunks.append(block)
    return "\n".join(chunks)


def body_for(text: str, rules: dict) -> tuple[str, str] | None:
    """Which file this session owes, and what to put in it."""
    match = REPORT.search(text)
    if not match:
        return None
    report = match.group(1)
    name = Path(report).name
    if name in (rules.get("fail_reports") or []) or operation() in (rules.get("fail") or []):
        return None
    if name.startswith("findings-"):
        lens = name.removeprefix("findings-").removesuffix(".json")
        table = rules.get("findings") or {}
        # `review-<lens>-<family>` keys a per-family answer; the bare lens is the default.
        key = operation().removeprefix("review-")
        findings = table.get(key, table.get(lens, []))
        return report, json.dumps({"lens": lens, "findings": findings}, indent=2)
    if name.startswith("verify-"):
        finding = FINDING.search(text)
        claim = CLAIM.search(text)
        chosen = dict(
            (rules.get("verify") or {}).get(
                "default", {"verdict": "PLAUSIBLE", "reason": "no rule matched"}
            )
        )
        for rule in (rules.get("verify") or {}).get("rules", []):
            if claim and rule.get("match", "") in claim.group(1):
                chosen = {key: value for key, value in rule.items() if key != "match"}
                break
        chosen["verification"] = (
            finding.group(1) if finding else name[len("verify-") : -len(".json")]
        )
        return report, json.dumps(chosen, indent=2)
    if name == "claims.json":
        return report, json.dumps(rules.get("claims", {"claims": []}), indent=2)
    if name == "body.json":
        return report, json.dumps(rules.get("body", {"body": "Recorded review body."}), indent=2)
    return report, "{}"


def main() -> None:
    rules = policy()
    out = sys.stdout
    session = "recording-session"
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        request = json.loads(line)
        method = request.get("method")
        result: dict = {}
        if method == "initialize":
            result = {"protocolVersion": 1, "agentCapabilities": {}, "authMethods": []}
        elif method == "session/new":
            # Never inside the reviewed worktree: that tree is allowlist-checked.
            record = os.environ.get("REVIEW_PR_RECORDING_OPTIONS")
            if record:
                Path(record).parent.mkdir(parents=True, exist_ok=True)
                Path(record).write_text(json.dumps(request.get("params", {})))
            models = list(rules.get("models") or DEFAULT_MODELS)
            # Plus whatever this session asked for: acpx refuses a `--model` the agent
            # did not advertise, so a hardcoded list makes every provider swap in the
            # template break the fixture instead of the lane it changed.
            asked = (
                ((request.get("params") or {}).get("_meta") or {})
                .get("claudeCode", {})
                .get("options", {})
                .get("model")
            )
            if isinstance(asked, str) and asked and asked not in models:
                models.insert(0, asked)
            result = {
                "sessionId": session,
                "models": {
                    "currentModelId": models[0],
                    "availableModels": [{"modelId": name, "name": name} for name in models],
                },
            }
        elif method in ("session/set_model", "session/set_config_option"):
            result = {}
        elif method == "session/prompt":
            text = prompt_text(request.get("params", {}))
            written = body_for(text, rules)
            if written:
                report, content = written
                target = Path(report)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(content + "\n")
            print(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "method": "session/update",
                        "params": {
                            "sessionId": session,
                            "update": {
                                "sessionUpdate": "usage_update",
                                "used": 1200,
                                "size": 200000,
                                "cost": {
                                    "amount": float(rules.get("cost_usd", 0.05)),
                                    "currency": "USD",
                                },
                            },
                        },
                    }
                ),
                file=out,
                flush=True,
            )
            result = {"stopReason": "end_turn"}
        if "id" in request:
            print(
                json.dumps({"jsonrpc": "2.0", "id": request["id"], "result": result}),
                file=out,
                flush=True,
            )


if __name__ == "__main__":
    main()

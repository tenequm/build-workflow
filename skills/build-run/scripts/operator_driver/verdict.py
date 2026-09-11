"""Counted verdict parsing ported from herdr; no engine-task or merge side effects."""

from __future__ import annotations

import json
import re
from pathlib import Path

DECLARED = {
    label: re.compile(rf"^\s*{label}\s*[:=]\s*(\d+)\b", re.IGNORECASE | re.MULTILINE)
    for label in ("certain", "plausible")
}

VERDICTS = ("do not merge", "merge after listed fixes", "merge as-is")

FILE_LINE = re.compile(r"\S+\.(go|py|ts|md|sql|yaml|yml):\d+")


def parse_verdict(review: Path) -> dict:
    if not review.exists():
        return {
            "review_present": False,
            "block": True,
            "verdict": "missing",
            "certain": 0,
            "plausible": 0,
            "counts_declared": False,
            "reason": "no blind-review.md",
        }
    raw = review.read_text()
    text = re.sub("```.*?```", "", raw, flags=re.DOTALL)
    tail_lines = [l.strip() for l in text.splitlines() if l.strip()][-3:]
    legal = re.findall(
        r"^Verdict:\s*(do not merge|merge after listed fixes|merge as-is)\s*$",
        "\n".join(tail_lines),
        re.IGNORECASE | re.MULTILINE,
    )
    verdict = legal[0].lower() if len(legal) == 1 else None
    certain_all = DECLARED["certain"].findall(text)
    plausible_all = DECLARED["plausible"].findall(text)
    problems = []
    if verdict is None:
        problems.append("no legal Verdict line in the last three lines")
    if len(certain_all) != 1:
        problems.append(f"{len(certain_all)} `Certain:` lines (need exactly 1)")
    if len(plausible_all) != 1:
        problems.append(f"{len(plausible_all)} `Plausible:` lines (need exactly 1)")
    if problems:
        malformed = {
            "review_present": True,
            "verdict": verdict or "unclear",
            "certain": int(certain_all[0]) if len(certain_all) == 1 else 0,
            "plausible": int(plausible_all[0]) if len(plausible_all) == 1 else 0,
            "counts_declared": False,
            "do_not_merge": "do not merge" in [value.lower() for value in legal],
            "merge_as_is": False,
            "block": True,
            "reason": "malformed review: " + "; ".join(problems),
        }
        vj = review.with_name("verdict.json")
        return _json_verdict(vj, malformed) if vj.exists() else malformed
    certain, plausible = (int(certain_all[0]), int(plausible_all[0]))
    prose = {
        "review_present": True,
        "verdict": verdict,
        "certain": certain,
        "plausible": plausible,
        "counts_declared": True,
        "do_not_merge": verdict == "do not merge",
        "merge_as_is": verdict == "merge as-is",
        "block": verdict == "do not merge",
    }
    vj = review.with_name("verdict.json")
    if vj.exists():
        return _json_verdict(vj, prose)
    if not prose["block"] and certain > 0 and (len(FILE_LINE.findall(raw)) < certain):
        return {
            **prose,
            "block": True,
            "reason": f"counted defects without evidence: certain={certain} but fewer file:line references in the review",
        }
    return prose


def _schema_problems(data: object) -> list[str]:
    if not isinstance(data, dict):
        return ["top level is not an object"]
    problems = []
    if data.get("verdict") not in VERDICTS:
        problems.append(f"verdict {data.get('verdict')!r} is not one of the three legal strings")
    for key in ("certain", "plausible"):
        v = data.get(key)
        if not isinstance(v, int) or isinstance(v, bool) or v < 0:
            problems.append(f"{key} is not a non-negative integer")
    ev = data.get("evidence")
    if not isinstance(ev, list):
        problems.append("evidence is not a list")
    else:
        for i, e in enumerate(ev):
            if (
                not isinstance(e, dict)
                or not isinstance(e.get("file"), str)
                or (not isinstance(e.get("line"), int))
                or isinstance(e.get("line"), bool)
                or (not isinstance(e.get("note"), str))
            ):
                problems.append(f"evidence[{i}] is not {{file: str, line: int, note: str}}")
        if (
            isinstance(data.get("certain"), int)
            and (not isinstance(data.get("certain"), bool))
            and (len(ev) != data["certain"])
        ):
            problems.append(
                f"{len(ev)} evidence entries for certain={data['certain']} (need exactly certain)"
            )
    return problems


def _json_verdict(vj: Path, prose: dict) -> dict:
    try:
        data = json.loads(vj.read_text())
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return {
            **prose,
            "block": True,
            "verdict_json": False,
            "reason": f"invalid verdict.json: {exc}",
        }
    problems = _schema_problems(data)
    if problems:
        return {
            **prose,
            "do_not_merge": prose.get("do_not_merge", False)
            or (isinstance(data, dict) and data.get("verdict") == "do not merge"),
            "block": True,
            "verdict_json": False,
            "reason": "invalid verdict.json: " + "; ".join(problems),
        }
    if not prose.get("counts_declared"):
        return {
            **prose,
            "do_not_merge": prose.get("do_not_merge", False) or data["verdict"] == "do not merge",
            "block": True,
            "verdict_json": False,
            "reason": "verdict.json is valid but the prose verdict block is malformed: "
            + str(prose.get("reason", "")),
        }
    mismatches = [
        f"{key}: json {data[key]!r} vs prose {prose[key]!r}"
        for key in ("verdict", "certain", "plausible")
        if data[key] != prose[key]
    ]
    if mismatches:
        return {
            **prose,
            "do_not_merge": prose.get("do_not_merge", False) or data["verdict"] == "do not merge",
            "block": True,
            "verdict_json": False,
            "reason": "verdict.json disagrees with the prose block: " + "; ".join(mismatches),
        }
    return {**prose, "verdict_json": True, "evidence": data["evidence"]}

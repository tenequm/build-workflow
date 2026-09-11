"""The findings contract. Stage 3, stage 4 and the precision ledger all read it.

Every field a later stage depends on is validated here, at the boundary where an
untrusted model wrote it, so no downstream stage has to guess what it received. A
findings file whose load-bearing fields are malformed is a failed attempt, never a
partially trusted one - but strictness is spent on fields that decide something, and
a purely descriptive one that a model invented is dropped rather than allowed to void
a report that is otherwise sound.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from operator_driver.storage import Park, canonical, digest

LENSES = (
    "cleanliness",
    "design",
    "efficiency",
    "gating",
    "implementation",
    "house-rules",
    "claims",
)
CATEGORIES = ("correctness", "convention", "cleanliness", "design", "efficiency")
IMPACTS = ("none", "security", "data_loss", "irreversible", "deploy")
VERDICTS = ("CONFIRMED", "PLAUSIBLE", "DROPPED", "UNVERIFIED")
SEVERITIES = ("SEVERE", "BLOCKING_FIX", "BLOCKING_QUESTION", "SUGGESTION")
TAGS = ("pre-existing", "out-of-diff", "injection", "heuristic")
# A diff finding must anchor to a hunk; a meta finding is about the pull request
# itself - its title, body, branch, a commit message or a check this workflow ran -
# and is body-only by construction rather than by anchor failure.
SCOPES = ("diff", "meta")
META_PREFIXES = ("PR:", "CHECK:")
RUBRIC_KINDS = ("command", "grep", "revert_test")
EXPECTATIONS = ("exit_zero", "exit_nonzero", "empty", "nonempty", "contains")

# A correctness or gating claim is the class the plan requires a PoC for; every other
# category settles on its rubric alone.
POC_CATEGORIES = ("correctness",)
POC_LENSES = ("gating",)
# Lenses whose findings are settled by an executed rubric rather than a failing repro.
RUBRIC_PROVES = ("implementation",)

# A suggestion is speculation with rollback, so it stays small enough to stage.
SUGGESTION_MAX_LINES = 12
CREDENTIAL = re.compile(
    r"(AKIA[0-9A-Z]{8,})|(gh[pousr]_[A-Za-z0-9]{16,})|(sk-[A-Za-z0-9]{20,})"
    r"|(-----BEGIN [A-Z ]*PRIVATE KEY-----)",
)


def redact(text: str) -> str:
    """Polish's rule as code: a finding names a credential, never reproduces one."""
    return CREDENTIAL.sub(lambda m: m.group(0)[:4] + "****", text)


def finding_id(lens: str, file: str, line: int, claim: str) -> str:
    return digest(canonical([lens, file, line, claim]))[:12]


def _string(entry: dict[str, Any], key: str, *, required: bool = True) -> str:
    value = entry.get(key)
    if value is None and not required:
        return ""
    if not isinstance(value, str) or not value.strip():
        raise Park(f"finding field {key!r} must be a non-empty string")
    return value.strip()


def _line(entry: dict[str, Any], key: str) -> int:
    value = entry.get(key)
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise Park(f"finding field {key!r} must be a positive integer line number")
    return value


def rubric(raw: object) -> dict[str, Any] | None:
    """A mechanical check a verifier can run, or nothing. Prose is not a rubric."""
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise Park("rubric must be an object or null")
    kind = raw.get("kind")
    if kind not in RUBRIC_KINDS:
        raise Park(f"rubric kind must be one of {RUBRIC_KINDS}")
    expect = raw.get("expect")
    if expect not in EXPECTATIONS:
        raise Park(f"rubric expect must be one of {EXPECTATIONS}")
    result: dict[str, Any] = {"kind": kind, "expect": expect}
    if expect == "contains":
        result["contains"] = _string(raw, "contains")
    if kind == "command":
        result["run"] = _string(raw, "run")
    elif kind == "grep":
        result["pattern"] = _string(raw, "pattern")
        result["path"] = _string(raw, "path", required=False) or "."
        if expect not in ("empty", "nonempty"):
            raise Park("a grep rubric expects empty or nonempty")
    else:
        result["test"] = _string(raw, "test")
        hunk = _string(raw, "hunk")
        if not re.fullmatch(r"[^\s:]+:\d+-\d+", hunk):
            raise Park("a revert_test rubric needs hunk as 'path:start-end'")
        result["hunk"] = hunk
        if expect != "exit_nonzero":
            raise Park("a revert_test rubric expects exit_nonzero: the test must flip")
    return result


def suggestion(raw: object) -> dict[str, Any] | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise Park("suggestion must be an object or null")
    replacement = raw.get("replacement")
    # An empty replacement is how GitHub says "delete these lines", and absence is
    # already the branch above. It reaches suggestions.apply() as a blank line rather
    # than a true deletion - cosmetically imperfect, gate-passing, and not a reason to
    # refuse the correct fix for an injected line.
    if not isinstance(replacement, str):
        raise Park("suggestion needs replacement text")
    lines = replacement.splitlines() or [""]
    if len(lines) > SUGGESTION_MAX_LINES:
        raise Park(f"suggestion exceeds {SUGGESTION_MAX_LINES} replacement lines")
    start = _line(raw, "start_line") if "start_line" in raw else None
    end = _line(raw, "line")
    if start is not None and start > end:
        raise Park("suggestion start_line must not exceed line")
    result: dict[str, Any] = {"replacement": replacement, "line": end}
    if start is not None:
        result["start_line"] = start
    return result


def normalize(entry: object, *, lens: str, producer: str) -> dict[str, Any]:
    if lens not in LENSES:
        raise Park(f"unknown lens: {lens!r}")
    if not isinstance(entry, dict):
        raise Park("each finding must be an object")
    category = entry.get("category")
    if category not in CATEGORIES:
        raise Park(f"finding category must be one of {CATEGORIES}")
    impact = entry.get("impact", "none")
    if impact not in IMPACTS:
        raise Park(f"finding impact must be one of {IMPACTS}")
    raw_tags = entry.get("tags", [])
    if not isinstance(raw_tags, list) or any(not isinstance(tag, str) for tag in raw_tags):
        raise Park("finding tags must be a list of strings")
    # Strict where a field decides something, tolerant where it only describes. Only
    # four tags change behaviour; a model that invents a descriptive fifth has still
    # produced a usable finding, so the extra is dropped and kept as evidence rather
    # than voiding the whole report. Measured 2026-09-11: one invented `docs-drift`
    # tag parked a run that had seven good sessions behind it.
    known = sorted({tag for tag in raw_tags if tag in TAGS})
    unknown = sorted({tag for tag in raw_tags if tag not in TAGS})
    scope = entry.get("scope", "diff")
    if scope not in SCOPES:
        raise Park(f"finding scope must be one of {SCOPES}")
    file = _string(entry, "file")
    if scope == "meta":
        if not file.startswith(META_PREFIXES):
            raise Park(f"a meta finding names its surface as PR:<part> or CHECK:<name>: {file!r}")
    elif Path(file).is_absolute() or ".." in Path(file).parts:
        raise Park(f"finding file must be a repository-relative path: {file!r}")
    line = _line(entry, "line")
    start_line = _line(entry, "start_line") if entry.get("start_line") is not None else None
    if start_line is not None and start_line > line:
        raise Park("start_line must not exceed line")
    claim = redact(_string(entry, "claim"))
    if len(claim.split()) < 3:
        raise Park("a claim must be a sentence, not a label")
    check = rubric(entry.get("rubric"))
    # The same rule as the tags above, for the same reason: the brief calls `suggestion`
    # optional and every consumer already guards for its absence, so a malformed one is
    # dropped and recorded rather than voiding a report four sessions paid for.
    try:
        change, dropped_suggestion = suggestion(entry.get("suggestion")), None
    except Park as exc:
        change, dropped_suggestion = None, str(exc)
    finding: dict[str, Any] = {
        "id": finding_id(lens, file, line, claim),
        "lens": lens,
        "producer": producer,
        "scope": scope,
        "file": file,
        "line": line,
        "category": category,
        "impact": impact,
        "claim": claim,
        "evidence": redact(_string(entry, "evidence")),
        "rubric": check,
        # The plan's demotion rule, applied where the rubric is read rather than
        # trusted to a later stage: no rubric, no verdict above SUGGESTION.
        "unverifiable": check is None,
        "tags": known,
        "dropped_tags": unknown,
        "follow_up": bool({"pre-existing", "out-of-diff"} & set(known)),
        "suggestion": change,
        "dropped_suggestion": dropped_suggestion,
        "verdict": "UNVERIFIED",
    }
    if start_line is not None:
        finding["start_line"] = start_line
    return finding


def load(path: Path, *, lens: str, producer: str) -> list[dict[str, Any]]:
    """Read one lens report. Anything unreadable parks the attempt, never degrades it."""
    try:
        data = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise Park(f"unreadable findings report {path.name}: {exc}") from exc
    if isinstance(data, dict):
        data = data.get("findings")
    if not isinstance(data, list):
        raise Park(f"findings report {path.name} is not a list of findings")
    findings = [normalize(entry, lens=lens, producer=producer) for entry in data]
    seen: set[str] = set()
    unique = []
    for finding in findings:
        if finding["id"] in seen:
            continue
        seen.add(finding["id"])
        unique.append(finding)
    return unique


def write(path: Path, findings: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"findings": findings}, indent=2, sort_keys=True) + "\n")


def merge(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One finding per (file, line, category); lenses that agree strengthen it.

    Cross-lens agreement is kept as evidence because the dual-family diff and the
    precision ledger both read it - a finding two lenses found is not the same
    object as one finding found once.
    """
    merged: dict[tuple[str, int, str], dict[str, Any]] = {}
    for finding in sorted(findings, key=lambda f: (f["file"], f["line"], f["category"], f["lens"])):
        key = (finding["file"], finding["line"], finding["category"])
        existing = merged.get(key)
        if existing is None:
            merged[key] = {**finding, "also_from": []}
            continue
        existing["also_from"] = sorted({*existing["also_from"], finding["lens"]})
        if finding.get("agreement"):
            existing["agreement"] = sorted(
                set(existing.get("agreement", [])) | set(finding["agreement"])
            )
        existing["tags"] = sorted(set(existing["tags"]) | set(finding["tags"]))
        existing["follow_up"] = existing["follow_up"] and finding["follow_up"]
        if IMPACTS.index(finding["impact"]) > IMPACTS.index(existing["impact"]):
            existing["impact"] = finding["impact"]
        # A rubric from any lens makes the merged finding verifiable.
        if existing["rubric"] is None and finding["rubric"] is not None:
            existing["rubric"] = finding["rubric"]
            existing["unverifiable"] = False
        if existing["suggestion"] is None and finding["suggestion"] is not None:
            existing["suggestion"] = finding["suggestion"]
    return list(merged.values())


def needs_poc(finding: dict[str, Any]) -> bool:
    """A model's correctness or gating claim confirms on a demonstration, never on prose.

    A finding this workflow produced itself is exempt: the check that created it already
    ran, so demanding a second demonstration of the same execution buys nothing.
    """
    if finding.get("producer") == "script":
        return False
    if finding["lens"] in RUBRIC_PROVES:
        # A documentation-versus-code mismatch has no failing test to write: its proof
        # is a grep that comes back empty or a command whose output contradicts the
        # claim. Demanding a runtime repro here would demote every true finding.
        return False
    return finding["category"] in POC_CATEGORIES or finding["lens"] in POC_LENSES


def needs_verifier(finding: dict[str, Any]) -> bool:
    """Whether a model has to read this claim, even when its rubric already passed.

    A claim-vs-implementation finding spans two artifacts: the statement and the code
    that decides it. Its rubric can only execute against the code, so a passing rubric
    proves one half and says nothing about the other. Measured 2026-09-11: 13 of 15
    findings confirmed with no verifier session at all, most of them on exactly that
    one-sided evidence. These queue for a blinded cross-family reader regardless.
    """
    if finding.get("producer") == "script":
        return False
    if needs_poc(finding):
        return True
    return finding["lens"] in RUBRIC_PROVES and finding["category"] == "correctness"


def presettle(finding: dict[str, Any], reason: str, verdict: str = "CONFIRMED") -> dict[str, Any]:
    """A finding whose deciding check has already executed carries its verdict with it."""
    if verdict not in VERDICTS:
        raise Park(f"verdict must be one of {VERDICTS}")
    return {
        **finding,
        "verdict": verdict,
        "verify": {
            "verifier": None,
            "reason": reason,
            "rubric": {"ran": True, "passed": verdict == "CONFIRMED"},
        },
    }

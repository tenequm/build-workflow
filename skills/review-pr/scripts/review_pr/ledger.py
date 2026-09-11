"""The precision ledger: append-only rows that turn the routing table into measurement.

Every finding this workflow produces lands here with its lens, its producing model,
the verifier's verdict, and - once a human has acted - its fate. After roughly twenty
pull requests that yields measured precision per (lens, model), which is the point:
the routing table in stages.yaml stops being priors and starts being evidence. The
same rows are the eval corpus a claim-vs-tool-call verifier would need later.

In-repo on purpose. This repository is public by design and the ledger is evidence; a
ledger under `.agents/` dies with the worktree that wrote it, a scar this project
already has.
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

from operator_driver.storage import Park, canonical

LEDGER = "docs/review-ledger/runs.jsonl"
FATES = ("posted", "author-fixed", "dropped-by-human", "superseded", "unknown")
EVENTS = ("finding", "fate", "run")


def path(repo_root: Path) -> Path:
    return repo_root / LEDGER


def append(ledger_path: Path, rows: list[dict[str, Any]]) -> int:
    """Append-only. A row is never rewritten; a correction is a later `fate` row."""
    for row in rows:
        if row.get("event") not in EVENTS:
            raise Park(f"ledger row event must be one of {EVENTS}")
        if row["event"] == "fate" and row.get("fate") not in FATES:
            raise Park(f"ledger fate must be one of {FATES}")
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("ab") as stream:
        for row in rows:
            stream.write(canonical({"at": time.time(), **row}) + b"\n")
    return len(rows)


def read(ledger_path: Path) -> list[dict[str, Any]]:
    if not ledger_path.is_file():
        return []
    rows = []
    for number, line in enumerate(ledger_path.read_text().splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError as exc:
            raise Park(f"{ledger_path}:{number} is not a ledger row: {exc}") from exc
    return rows


def rows_for(
    summary: dict[str, Any], run_id: str, sessions: dict[str, Any]
) -> list[dict[str, Any]]:
    """One row per finding, keyed to the transcripts that produced and verified it."""
    rows: list[dict[str, Any]] = [
        {
            "event": "run",
            "run": run_id,
            "repo": summary["repo"],
            "number": summary["number"],
            "head": summary["head"],
            "action": summary["action"],
            "counts": summary["counts"],
            "evidence": {
                key: summary["evidence"].get(key)
                for key in ("wall_s", "sessions", "tier", "capture")
            },
        }
    ]
    for finding in summary["findings"]:
        verify = finding.get("verify") or {}
        rubric = verify.get("rubric") or {}
        rows.append(
            {
                "event": "finding",
                "run": run_id,
                "repo": summary["repo"],
                "number": summary["number"],
                "finding": finding["id"],
                "lens": finding["lens"],
                "producer": finding["producer"],
                "producer_model": finding.get("producer_model"),
                "verifier": verify.get("verifier"),
                "verifier_model": (verify.get("session") or {}).get("model"),
                "category": finding["category"],
                "impact": finding["impact"],
                "rubric_kind": (finding.get("rubric") or {}).get("kind"),
                "rubric_passed": rubric.get("passed"),
                "gold_gate": (verify.get("gold_gate") or {}).get("passed"),
                "verdict": finding["verdict"],
                "severity": finding.get("severity"),
                "follow_up": finding["follow_up"],
                "agreement": finding.get("agreement", []),
                "sessions": sessions.get(finding["id"], {}),
            }
        )
    return rows


def record_fate(ledger_path: Path, run_id: str, finding_id: str, fate: str, note: str = "") -> None:
    append(
        ledger_path,
        [{"event": "fate", "run": run_id, "finding": finding_id, "fate": fate, "note": note}],
    )


def precision(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Measured precision per (lens, producing model). Acted-on over posted.

    A precision-tuned reviewer gets 46% of its comments acted on; that ratio, per lens,
    is this tool's own quality metric.
    """
    fates: dict[str, str] = {}
    for row in rows:
        if row["event"] == "fate":
            fates[row["finding"]] = row["fate"]
    buckets: dict[tuple[str, str], dict[str, int]] = defaultdict(
        lambda: {"found": 0, "confirmed": 0, "posted": 0, "acted": 0, "dropped": 0}
    )
    for row in rows:
        if row["event"] != "finding":
            continue
        key = (row["lens"], row.get("producer_model") or row["producer"])
        bucket = buckets[key]
        bucket["found"] += 1
        if row["verdict"] == "CONFIRMED":
            bucket["confirmed"] += 1
        if row["verdict"] == "DROPPED":
            bucket["dropped"] += 1
        fate = fates.get(row["finding"])
        if fate in ("posted", "author-fixed", "dropped-by-human"):
            bucket["posted"] += 1
        if fate == "author-fixed":
            bucket["acted"] += 1
    report = {}
    for (lens, model), bucket in sorted(buckets.items()):
        report[f"{lens}/{model}"] = {
            **bucket,
            "precision": round(bucket["acted"] / bucket["posted"], 3) if bucket["posted"] else None,
            "confirm_rate": round(bucket["confirmed"] / bucket["found"], 3)
            if bucket["found"]
            else None,
        }
    return {
        "buckets": report,
        "findings": sum(b["found"] for b in buckets.values()),
        "with_fate": len(fates),
    }

"""The dual-family lens diff: where the stage-3 budget should go.

Cross-family ensembles realise 43-44% of the theoretical independence gain against
under 30% for same-model runs, and disagreement alone detects about two thirds of
incorrect programs at zero false positives. So two families run the same lens and the
finding sets are differenced: agreement is cheap confirmation, disagreement is what
gets a verifier session.
"""

from __future__ import annotations

from typing import Any

LINE_WINDOW = 3


def _same(left: dict[str, Any], right: dict[str, Any]) -> bool:
    return (
        left["file"] == right["file"]
        and left["category"] == right["category"]
        and abs(left["line"] - right["line"]) <= LINE_WINDOW
    )


def diff_sets(by_family: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    """Mark every finding with the families that independently produced it."""
    families = sorted(by_family)
    if len(families) < 2:
        only = families[0] if families else None
        return {
            "families": families,
            "findings": [
                {**finding, "agreement": [only] if only else []}
                for finding in by_family.get(only or "", [])
            ],
            "agreed": 0,
            "disagreed": len(by_family.get(only or "", [])),
        }
    marked: list[dict[str, Any]] = []
    for family in families:
        others = [other for other in families if other != family]
        for finding in by_family[family]:
            agreement = [family] + [
                other
                for other in others
                if any(_same(finding, candidate) for candidate in by_family[other])
            ]
            marked.append({**finding, "agreement": sorted(agreement)})
    # One row per claim: a claim both families found appears once, carrying both.
    unique: list[dict[str, Any]] = []
    for finding in sorted(
        marked, key=lambda f: (f["file"], f["line"], f["category"], f["producer"])
    ):
        if any(_same(finding, kept) for kept in unique):
            for kept in unique:
                if _same(finding, kept):
                    kept["agreement"] = sorted(set(kept["agreement"]) | set(finding["agreement"]))
                    # Whatever either family could state, the surviving row keeps: a
                    # rubric makes it verifiable and a suggestion makes it fixable, and
                    # dropping one because the other family sorted first loses real work.
                    if kept["rubric"] is None and finding["rubric"] is not None:
                        kept["rubric"] = finding["rubric"]
                        kept["unverifiable"] = False
                    if kept.get("suggestion") is None and finding.get("suggestion") is not None:
                        kept["suggestion"] = finding["suggestion"]
                        start = finding.get("start_line", kept.get("start_line"))
                        if start is not None:
                            kept["start_line"] = start
                    if kept.get("impact") == "none" and finding.get("impact", "none") != "none":
                        kept["impact"] = finding["impact"]
                    break
            continue
        unique.append(dict(finding))
    agreed = [finding for finding in unique if len(finding["agreement"]) > 1]
    return {
        "families": families,
        "findings": unique,
        "agreed": len(agreed),
        "disagreed": len(unique) - len(agreed),
    }

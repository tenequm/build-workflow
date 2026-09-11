"""Stage 3: verification, in the order that makes each step cheap.

The rubric runs first and in the driver, because execution is ground truth and costs
nothing. A verifier model is spent only where execution cannot settle the question, or
where the claim's class demands a proof of concept. Every verifier is a different
family than the claim's producer, is blind to the pull request body and to who made
the claim, and its repro must survive the gold gate before it can confirm anything.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from operator_driver.storage import Ledger, Park

from . import briefs, config
from . import findings as findings_mod
from . import rubric as rubric_mod
from .runner import Task

VERDICTS = ("CONFIRMED", "PLAUSIBLE", "DROPPED")


def opposite(plan: dict[str, Any], producer: str) -> str:
    """A judge is more than 50% likelier to pass its own model's output."""
    table = plan.get("routing", {}).get("opposite", {})
    chosen = table.get(producer)
    if chosen and chosen != producer:
        return chosen
    other = [name for name in sorted(plan["roles"]["verifier"]["models"]) if name != producer]
    if not other:
        raise Park(f"no family available to verify a {producer} finding")
    return other[0]


def second_reading(finding: dict[str, Any]) -> bool:
    """Whether two families independently made this claim.

    Cross-family agreement is the second reading a two-sided claim needs: the rubric
    executed the implementation half, and a second family independently asserting the
    claim half is stronger evidence than one verifier's re-read - disagreement alone
    detects about two thirds of incorrect programs at zero false positives. Until this
    was wired in, `agreement` was computed, written to the ledger, and read by
    nothing that decided anything.
    """
    return len(finding.get("agreement") or []) > 1


def priority(finding: dict[str, Any]) -> tuple[int, int, int, str]:
    """Correctness and gating first; then contested claims; then impact."""
    poc = 0 if findings_mod.needs_verifier(finding) else 1
    contested = 0 if not second_reading(finding) else 1
    impact = 0 if finding["impact"] != "none" else 1
    return (poc, contested, impact, finding["id"])


def rubrics(
    candidates: list[dict[str, Any]],
    sidecar: dict[str, Any],
    *,
    tier: str,
) -> dict[str, dict[str, Any]]:
    """Execute every stated rubric. This is the only part of verification that is truth."""
    return {
        finding["id"]: rubric_mod.execute(finding, sidecar, tier=tier) for finding in candidates
    }


def select(
    candidates: list[dict[str, Any]],
    observed: dict[str, dict[str, Any]],
    *,
    cap: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Split into findings worth a verifier session and findings their rubric settles.

    A claim whose rubric passed and whose class needs no proof of concept is already
    decided. A two-sided claim (needs_verifier) is decided without a session only when
    a second family independently made it AND its rubric passed - agreement is the
    second reading. A claim that needs a proof of concept always queues: agreement is
    two opinions, not a demonstration. Everything else queues, cut at the cap.
    """
    queue: list[dict[str, Any]] = []
    settled: list[dict[str, Any]] = []
    for finding in candidates:
        result = observed[finding["id"]]
        decided = result["passed"] and (
            not findings_mod.needs_verifier(finding)
            or (not findings_mod.needs_poc(finding) and second_reading(finding))
        )
        if decided:
            settled.append(finding)
        else:
            queue.append(finding)
    queue.sort(key=priority)
    return queue[:cap], settled + queue[cap:]


def _report(path: Path, finding_id: str, tree: str | None = None) -> dict[str, Any]:
    try:
        data = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise Park(f"unreadable verification report {path.name}: {exc}") from exc
    if not isinstance(data, dict) or data.get("verification") != finding_id:
        raise Park(f"verification report is for another finding: {path.name}")
    if data.get("verdict") not in VERDICTS:
        raise Park(f"verification verdict must be one of {VERDICTS}: {path.name}")
    reason = data.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        raise Park(f"verification report states no reason: {path.name}")
    repro = data.get("repro")
    if repro is not None and (not isinstance(repro, str) or not repro.strip()):
        raise Park(f"verification repro must be a shell script or null: {path.name}")
    # A replacement rubric is an optimisation - a sharper check than the one the claim
    # arrived with. The verdict and the reason are what decide anything, so a malformed
    # replacement is dropped and recorded rather than voiding a verification that is
    # otherwise complete. Measured 2026-09-11: one bad `expect` parked a whole run.
    replacement, rejected = None, None
    try:
        replacement = findings_mod.rubric(data.get("rubric"))
    except Park as exc:
        rejected = str(exc)
    # A session may write a demonstration into its own worktree (runner.SCRATCH), and
    # that worktree is gone by the time any rubric executes - rubrics run against the
    # shared tree. So a replacement that names a file the session made cannot run, and
    # a rubric that cannot run must never reach a verdict. Same channel: dropped and
    # recorded, because the verdict and the reason are what decide anything.
    if replacement and replacement["kind"] == "command" and tree:
        blocked = rubric_mod.unrunnable(replacement["run"], Path(tree))
        if blocked:
            replacement, rejected = None, blocked
    return {
        "verdict": data["verdict"],
        "reason": findings_mod.redact(reason.strip()),
        "repro": repro,
        "rubric": replacement,
        "rejected_rubric": rejected,
    }


def settle(
    finding: dict[str, Any],
    observed: dict[str, Any],
    session: dict[str, Any] | None,
    sidecar: dict[str, Any],
    *,
    tier: str,
) -> dict[str, Any]:
    """Assign one finding's verdict from execution first and opinion second."""
    evidence: dict[str, Any] = {"rubric": observed}
    if session is None:
        if observed["passed"]:
            verdict = "CONFIRMED"
            reason = "the stated rubric passed"
        elif observed["ran"]:
            verdict = "PLAUSIBLE"
            reason = f"the stated rubric did not decide it: {observed.get('reason', 'expectation unmet')}"
        else:
            verdict = "PLAUSIBLE"
            reason = observed.get("reason", "no mechanical check was available")
        if findings_mod.needs_poc(finding) and verdict == "CONFIRMED":
            # This class confirms on a demonstration, never on a rubric alone.
            verdict = "PLAUSIBLE"
            reason = "the rubric passed but no proof of concept was produced"
        elif findings_mod.needs_verifier(finding) and verdict == "CONFIRMED":
            if second_reading(finding):
                reason = "the stated rubric passed and two families independently made this claim"
            else:
                # A two-sided claim past the session cap, made by one family: the
                # rubric checked the implementation, and nothing read the claim side.
                verdict = "PLAUSIBLE"
                reason = (
                    "the rubric checked the implementation side only, and no verifier "
                    "read it against the claim"
                )
        return {
            **finding,
            "verdict": verdict,
            "verify": {**evidence, "reason": reason, "verifier": None},
        }
    evidence["session"] = {
        "operation": session["operation"],
        "family": session["family"],
        "model": session["model"],
        "acp_session": session["acp"]["session_id"],
        "cost_usd": session["cost_usd"],
    }
    if not session["ok"]:
        return {
            **finding,
            "verdict": "PLAUSIBLE",
            "verify": {
                **evidence,
                "verifier": session["family"],
                "reason": "the verifier session produced no usable report: "
                + "; ".join(session["problems"]),
            },
        }
    report = session["verification"]
    evidence["verifier_report"] = report
    if report["verdict"] == "DROPPED":
        return {
            **finding,
            "verdict": "DROPPED",
            "verify": {**evidence, "verifier": session["family"], "reason": report["reason"]},
        }
    replaced = None
    if report["rubric"] is not None and report["rubric"] != finding.get("rubric"):
        replaced = rubric_mod.execute({**finding, "rubric": report["rubric"]}, sidecar, tier=tier)
        evidence["replacement_rubric"] = replaced
    mechanical = observed["passed"] or bool(replaced and replaced["passed"])
    if findings_mod.needs_poc(finding):
        if not report["repro"]:
            return {
                **finding,
                "verdict": "PLAUSIBLE",
                "verify": {
                    **evidence,
                    "verifier": session["family"],
                    "reason": "no proof of concept was produced, so the claim is "
                    "demoted: " + report["reason"],
                },
            }
        gold = rubric_mod.gold_gate(report["repro"], sidecar, tier=tier)
        evidence["gold_gate"] = gold
        if not gold["passed"]:
            return {
                **finding,
                "verdict": "PLAUSIBLE",
                "verify": {
                    **evidence,
                    "verifier": session["family"],
                    "reason": "the proof of concept did not survive the gold gate: "
                    + gold["reason"],
                },
            }
        return {
            **finding,
            "verdict": "CONFIRMED",
            "verify": {
                **evidence,
                "verifier": session["family"],
                "reason": "a proof of concept fails on the head and passes on base: "
                + report["reason"],
            },
        }
    if mechanical:
        # A two-sided claim's rubric reaches only the implementation half, so a passing
        # rubric confirms it only when the verifier - who read the claim half - also
        # confirmed. Found by the cross-family review of 2026-09-11: the rubric was
        # overriding a verifier that had just said PLAUSIBLE.
        if not findings_mod.needs_verifier(finding) or report["verdict"] == "CONFIRMED":
            return {
                **finding,
                "verdict": "CONFIRMED",
                "verify": {
                    **evidence,
                    "verifier": session["family"],
                    "reason": "a rubric decided it: " + report["reason"],
                },
            }
        return {
            **finding,
            "verdict": "PLAUSIBLE",
            "verify": {
                **evidence,
                "verifier": session["family"],
                "reason": "the rubric checked the implementation side, and the verifier "
                "did not confirm the claim side: " + report["reason"],
            },
        }
    return {
        **finding,
        "verdict": "PLAUSIBLE",
        "verify": {
            **evidence,
            "verifier": session["family"],
            "reason": "it holds on re-read with no mechanical proof: " + report["reason"],
        },
    }


def verify(
    candidates: list[dict[str, Any]],
    sidecar: dict[str, Any],
    plan: dict[str, Any],
    ledger: Ledger,
    paths: dict[str, Path],
    *,
    tier: str,
    launch,
) -> dict[str, Any]:
    """Run stage 3 over the in-diff findings and return them carrying verdicts.

    `launch` runs a batch of sessions; the caller supplies it so a test can drive this
    stage without a provider, and so the real batch stays one code path.
    """
    # A follow-up is reported but never enters the verdict, so it is never verified:
    # the stage-3 budget belongs to claims that can still change the outcome.
    settled_already = [f for f in candidates if f["verdict"] != "UNVERIFIED" or f["follow_up"]]
    candidates = [f for f in candidates if f["verdict"] == "UNVERIFIED" and not f["follow_up"]]
    observed = rubrics(candidates, sidecar, tier=tier)
    cap = int(plan["bounds"]["max_verifier_sessions"])
    queued, unqueued = select(candidates, observed, cap=cap)
    tasks: list[Task] = []
    for finding in queued:
        family = opposite(plan, finding["producer"])
        spec = config.role_spec(plan, "verifier", family=family)
        brief, report, witness = briefs.verifier(finding, sidecar, paths)
        tasks.append(
            Task(
                operation=f"verify-{finding['id']}",
                key=f"verify-{finding['id']}",
                brief=brief,
                report=report,
                witness=witness,
                spec=spec,
                lens=finding["lens"],
                family=family,
                meta={"finding": finding["id"], "producer": finding["producer"]},
            )
        )
    receipts = launch(tasks) if tasks else {}
    sessions: dict[str, dict[str, Any]] = {}
    for task in tasks:
        receipt = receipts[task.operation]
        finding_id = str(task.meta["finding"])
        if receipt["ok"]:
            report_path = (
                ledger.directory / "sessions" / receipt["operation"] / Path(task.report).name
            )
            receipt = {
                **receipt,
                "verification": _report(report_path, finding_id, sidecar.get("tree")),
            }
        sessions[finding_id] = receipt
    resolved = (
        [
            settle(
                finding, observed[finding["id"]], sessions.get(finding["id"]), sidecar, tier=tier
            )
            for finding in queued
        ]
        + [
            settle(finding, observed[finding["id"]], None, sidecar, tier=tier)
            for finding in unqueued
        ]
        + settled_already
    )
    return {
        "tier": tier,
        "cap": cap,
        "sessions": len(tasks),
        "settled_by_rubric": len(unqueued),
        "findings": sorted(resolved, key=lambda f: (f["file"], f["line"], f["id"])),
        "receipts": receipts,
    }

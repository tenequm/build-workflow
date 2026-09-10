"""Workflow obligations, reservations, and receipt-bound phase reactions."""

from __future__ import annotations

import time

from .ceremony import judge, reaction
from .engine import execute
from .spec import Build, git
from .storage import Ledger, Park, canonical, digest


class Bounds:
    def __init__(self, build: Build, ledger: Ledger):
        self.build, self.ledger = build, ledger

    def check(self):
        start = self.ledger.last("build_started")
        if start and time.time() - start["time"] > self.build.bounds["max_wall_s"]:
            raise Park("whole-build wall-clock limit reached")

    def reserve(self, operation: str, amount: float):
        self.check()
        existing = self.ledger.last("reservation", operation=operation)
        if existing:
            if existing["reserved_usd"] != amount:
                raise Park("spend reservation changed")
            return
        reservations = [row for row in self.ledger.events if row["event"] == "reservation"]
        if len(reservations) >= self.build.bounds["max_attempts"]:
            raise Park("whole-build attempt limit reached")
        committed = 0.0
        for row in reservations:
            settlement = self.ledger.last(
                "native_closed", operation=row["operation"]
            ) or self.ledger.last("judge_receipt", operation=row["operation"])
            # Native auxiliary/model accounting is not a complete final invoice.
            # Keep its whole reservation charged even when observed rows are low.
            # A judge that reported a cost settles at it; one whose transport reports
            # none (a subscription agent) is unmeasured, not free, so it settles at
            # its reservation like a native run.
            measured = settlement["cost_usd"] if settlement else None
            if settlement and settlement["event"] == "judge_receipt" and measured is not None:
                committed += measured
            else:
                committed += max(row["reserved_usd"], measured or 0)
        if committed + amount > self.build.bounds["max_spend_usd"]:
            raise Park("whole-build spend limit cannot cover another attempt")
        self.ledger.append("reservation", operation=operation, reserved_usd=amount)


def fix_input(build: Build, receipt: dict) -> dict:
    dest = build.run_dir / "judge" / receipt["operation"]
    result = {"receipt": receipt, "receipt_sha256": digest(canonical(receipt)), "artifacts": {}}
    # Embed exact bytes as UTF-8 text in the task description. No branch-local
    # mutable path or inaccessible detached-worktree location is needed by a fix.
    for name in ("blind-review.md", "verdict.json", "scorecard.md"):
        if name not in receipt["artifacts"]:
            continue
        raw = (dest / name).read_bytes()
        if digest(raw) != receipt["artifacts"][name]:
            raise Park("fix review input differs from its immutable receipt")
        result["artifacts"][name] = {"sha256": digest(raw), "utf8": raw.decode()}
    return result


def run_build(build: Build, ledger: Ledger, *, execute_run=execute, judge_run=judge) -> dict:
    started = ledger.last("build_started")
    if not started:
        raise Park("build has no frozen readiness receipt; run readiness before execution")
    if started["fingerprint"] != build.fingerprint or started["branch"] != build.branch:
        raise Park("build input identity changed")
    base = started["base"]
    if git(build.root, "rev-parse", f"refs/build/base/{build.slug}") != base:
        raise Park("write-once build base moved")
    build.verify_pins(base)
    bounds = Bounds(build, ledger)
    parked = ledger.last("parked")
    if parked:
        raise Park(
            f"build is parked: {parked['reason']}; preserve its evidence for explicit resolution"
        )
    completed = ledger.last("build_completed")
    if completed:
        if git(build.root, "rev-parse", build.branch) != completed["tip"]:
            raise Park("integration moved after build completion")
        return completed
    for phase in build.phases:
        if ledger.last("phase_accepted", phase=phase["name"]):
            continue
        if not ledger.last("native_intent", operation=phase["name"]):
            prior = ledger.last("phase_accepted")
            expected_tip = prior["tip"] if prior else base
            if git(build.root, "rev-parse", build.branch) != expected_tip:
                raise Park("integration moved between accepted phases")
        closed = execute_run(
            build,
            ledger,
            phase["steps"],
            phase["name"],
            base,
            reserve=bounds.reserve,
            check_bounds=bounds.check,
        )
        sequence, malformed = 0, 0
        while True:
            bounds.check()
            operation = f"{phase['name']}-judge-{sequence}"
            # Historical reviews are replayed only into their already-bound
            # reaction. A new ceremony requires the current ref to match its input.
            decision = ledger.last("reaction", operation=operation)
            if decision is None and git(build.root, "rev-parse", build.branch) != closed["tip"]:
                raise Park("integration moved before a new judge ceremony")
            bounds.reserve(operation, phase["judge"]["budget_usd"])
            receipt = judge_run(
                build, ledger, phase, base, closed["tip"], operation, timeout_check=bounds.check
            )
            seal = digest(canonical(receipt))
            action = reaction(receipt["verdict"], malformed)
            if decision:
                if decision["receipt_hash"] != seal or decision["action"] != action:
                    raise Park("reaction no longer matches its immutable attempt receipt")
            else:
                decision = ledger.append(
                    "reaction",
                    operation=operation,
                    phase=phase["name"],
                    receipt_hash=seal,
                    action=action,
                    tip=closed["tip"],
                )
            if action == "park":
                raise Park("judge verdict requires operator resolution")
            if action == "accept":
                if git(build.root, "rev-parse", build.branch) != closed["tip"]:
                    raise Park("integration moved before phase acceptance")
                ledger.append(
                    "phase_accepted", phase=phase["name"], receipt_hash=seal, tip=closed["tip"]
                )
                break
            if action == "fix":
                evidence = receipt["verdict"].get("evidence", [])
                if not evidence or not build.fix_scope_covers(phase, evidence):
                    raise Park(
                        "actionable review is outside the pinned fix scope or has no structured evidence"
                    )
                fix_operation = f"{phase['name']}-fix-{sequence}"
                if not ledger.last("native_intent", operation=fix_operation):
                    if git(build.root, "rev-parse", build.branch) != closed["tip"]:
                        raise Park("integration moved before fix dispatch")
                closed = execute_run(
                    build,
                    ledger,
                    [phase["fix"]],
                    fix_operation,
                    base,
                    reserve=bounds.reserve,
                    check_bounds=bounds.check,
                    fix_input=fix_input(build, receipt),
                )
                malformed = 0
            else:
                malformed += 1
            sequence += 1
    tip = git(build.root, "rev-parse", build.branch)
    return ledger.append("build_completed", tip=tip, base=base, phases=len(build.phases))

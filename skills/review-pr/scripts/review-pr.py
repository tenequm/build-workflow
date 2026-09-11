#!/usr/bin/env python3
"""/review-pr: stamp a review workspace for a pull request, run it, and stop.

Subcommands run one stage boundary each, so a failure is inspectable where it
happened. `run` executes stages 0 to 4 in order. Nothing posts without `post`, and
`post` re-checks the pull request's state before it does.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from operator_driver.storage import Ledger, Park  # noqa: E402
from review_pr import (  # noqa: E402
    checkout,
    config,
    houserules,
    pipeline,
    readiness,
    verdictcalc,
)
from review_pr import (
    gate as gate_mod,
)
from review_pr import (
    ledger as ledger_mod,
)
from review_pr.proc import command  # noqa: E402


def _plan(args: argparse.Namespace) -> dict:
    return config.load(Path(args.stages) if getattr(args, "stages", None) else None)


def cmd_ready(args: argparse.Namespace) -> int:
    side = checkout.sidecar(Path(args.dest)) if args.dest and Path(args.dest).exists() else None
    report = readiness.check(
        _plan(args), sidecar=side, capture=not args.no_pond, requested_tier=args.tier
    )
    for row in report["checks"]:
        print(f"{'ok  ' if row['ok'] else 'FAIL'} {row['check']:22} {row['detail']}")
    print(f"\nsandbox tier: {report['tier']}")
    print(
        "readiness: " + ("READY" if report["ok"] else "REFUSED: " + ", ".join(report["blocking"]))
    )
    return 0 if report["ok"] else 1


def cmd_setup(args: argparse.Namespace) -> int:
    pr = checkout.facts(
        args.source,
        number=args.pr,
        repo=args.repo,
        descriptor=Path(args.facts) if args.facts else None,
    )
    repo_path = Path(args.repo_path or pr.get("repoPath") or ".").resolve()
    side = checkout.prepare(
        Path(args.dest), pr=pr, repo_path=repo_path, gate_override=args.gate_cmd, rules=args.rules
    )
    if args.test_cmd or args.sandbox_image:
        path = Path(args.dest) / "review.json"
        data = json.loads(path.read_text())
        if args.test_cmd:
            data["test_cmd"] = args.test_cmd
        if args.sandbox_image:
            data["sandbox_image"] = args.sandbox_image
        path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
        side = data
    print(f"workspace:     {args.dest}")
    print(f"pull request:  {side.get('url') or side['repo']}#{side['number']} by {side['author']}")
    print(f"range:         {side['base'][:12]}..{side['head'][:12]} on {side['base_branch']}")
    print(
        f"reviewable:    {len(side['reviewable_files'])} files, {side['changed_lines']} lines"
        f" ({len(side['excluded_files'])} generated files excluded)"
    )
    print(f"validation:    {side['gate']['command']!r} from {side['gate']['source']}")
    other = side["gate"].get("candidates") or []
    if other:
        print(
            f"               not chosen: {', '.join(repr(value) for value in other[:4])}"
            " (override with --gate-cmd)"
        )
    print(f"rules:         {side['rules']}")
    family = side["author_family"]
    print(f"author family: {family['family']} ({family['confidence']})")
    if side["gate_edited"]:
        print("note:          this pull request edits the validation command; that is a finding")
    if side["fast_path"]:
        print(
            f"\nfast path: {side['changed_lines']} changed lines is under "
            f"{side['fast_path_threshold']}. The driver overhead loses to the interactive "
            "skill here - review this one with /polish."
        )
        if not getattr(args, "force", False):
            return 2
        print("--force: reviewing it here anyway")
    return 0


def _tier(args: argparse.Namespace, side: dict) -> str:
    return readiness.check(
        _plan(args), sidecar=side, capture=not args.no_pond, requested_tier=args.tier
    )["tier"]


def cmd_lint(args: argparse.Namespace) -> int:
    """Stage 0 alone: the mechanical rules, no model, seconds."""
    dest = Path(args.dest).resolve()
    side = checkout.sidecar(dest)
    pr = json.loads((dest / "pr.json").read_text())
    diff = (dest / side["diff"]).read_text(errors="replace")
    result = houserules.lint(side, pr, diff, tier=_tier(args, side))
    print(f"rules: {result['rules']}  sandbox: {result['tier']}\n")
    for check in result["checks"]:
        print(f"{check['result']:8} {check['rule']:24} {check['detail']}")
    print(f"\n{len(result['findings'])} finding(s) before any model ran")
    for finding in result["findings"]:
        where = (
            finding["file"]
            if finding["scope"] == "meta"
            else f"{finding['file']}:{finding['line']}"
        )
        print(f"  [{finding['category']}] {where} - {finding['claim']}")
    return 0


def cmd_gate(args: argparse.Namespace) -> int:
    """Stage 1 alone: the base-pinned command, once, on a cold linter cache."""
    dest = Path(args.dest).resolve()
    side = checkout.sidecar(dest)
    result = gate_mod.run(side, tier=_tier(args, side))
    print(f"command:  {result['command']!r} (from {result['provenance']['source']})")
    print(f"sandbox:  {result['tier']}   cold caches: {', '.join(result['cold_caches'])}")
    print(f"exit:     {result['returncode']}{' (timed out)' if result['timed_out'] else ''}")
    tail = (result["stderr_tail"] or result["stdout_tail"]).strip().splitlines()[-20:]
    if tail:
        print("\n" + "\n".join(tail))
    print(f"\n{len(result['findings'])} finding(s)")
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    dest = Path(args.dest).resolve()
    side = checkout.sidecar(dest)
    plan = _plan(args)
    report = readiness.check(plan, sidecar=side, capture=not args.no_pond, requested_tier=args.tier)
    if not args.skip_ready:
        readiness.require(report)
    ledger = Ledger(dest)
    summary = pipeline.run(
        dest, side, plan, ledger, tier=report["tier"], capture=not args.no_pond, run_id=args.run_id
    )
    print((dest / "report.md").read_text())
    print(
        f"\nartifacts: {dest}/report.md, {dest}/summary.json"
        + (f", {dest}/pr-review.json" if summary["action"] != "skip" else "")
    )
    print(f"ledger:    {summary['ledger']}")
    if summary["anchor_violations"]:
        print(f"\nanchor violations withheld from the payload: {summary['anchor_violations']}")
    return 0


def cmd_post(args: argparse.Namespace) -> int:
    dest = Path(args.dest).resolve()
    side = checkout.sidecar(dest)
    summary = json.loads((dest / "summary.json").read_text())
    payload = dest / "pr-review.json"
    if summary["action"] == "skip" or not payload.is_file():
        print(f"nothing to post: {summary.get('skip_reason') or 'no payload was assembled'}")
        return 1
    if args.confirm != summary["action"]:
        print(
            f"refusing: this review recommends {summary['action']!r}; "
            f"pass --confirm {summary['action']} or name the action you are overriding to"
        )
        if args.confirm not in verdictcalc.ACTIONS:
            return 1
        print(f"overriding {summary['action']} -> {args.confirm}")
        payload_data = json.loads(payload.read_text())
        payload_data["event"] = verdictcalc.EVENTS[args.confirm]
        payload.write_text(json.dumps(payload_data, indent=2) + "\n")
    # The state gate, re-checked: a head that moved, a merge, or a draft invalidates
    # the verdict rather than the payload.
    fresh = checkout.facts("gh", number=side["number"], repo=side["repo"], descriptor=None)
    if fresh.get("headRefOid") != side["head"]:
        print(
            f"refusing: head moved {side['head'][:12]} -> {str(fresh.get('headRefOid'))[:12]}; "
            "re-run the review against the new head"
        )
        return 1
    skip = verdictcalc.state_gate(fresh)
    if skip:
        print(f"refusing: {skip}")
        return 1
    argv = [
        "gh",
        "api",
        "--method",
        "POST",
        f"repos/{side['repo']}/pulls/{side['number']}/reviews",
        "--input",
        str(payload),
    ]
    code, out, err = command(argv, dest, timeout=180)
    sys.stdout.write(out.decode(errors="replace"))
    if code:
        sys.stderr.write(err.decode(errors="replace"))
        return code
    rows = [
        {
            "event": "fate",
            "run": summary.get("run", "unknown"),
            "finding": finding["id"],
            "fate": "posted",
        }
        for finding in summary["findings"]
        if finding.get("severity")
    ]
    ledger_mod.append(ledger_mod.path(Path(side["repo_path"])), rows)
    print(f"\nposted {len(rows)} finding(s) as one review under your account")
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    """What a run has durably finished, what is live, what failed - from disk alone."""
    from operator_driver.processes import alive

    dest = Path(args.dest).resolve()
    products = sorted(path.stem for path in (dest / "products").glob("*.json"))
    print(f"stage products: {', '.join(products) or 'none yet'}")
    receipts = sorted((dest / "sessions").glob("*/receipt.json"))
    ok = sum(1 for path in receipts if json.loads(path.read_text())["ok"])
    print(f"sessions:       {len(receipts)} settled ({ok} ok, {len(receipts) - ok} failed)")
    live = []
    for path in sorted((dest / "processes").glob("*.json")):
        if path.name.endswith(".exit.json"):
            continue
        receipt = json.loads(path.read_text())
        if not path.with_suffix("").with_suffix(".exit.json").is_file() and alive(receipt):
            live.append(f"{path.stem} (pid {receipt['pid']})")
    print(f"live processes: {', '.join(live) or 'none'}")
    if (dest / "summary.json").is_file():
        summary = json.loads((dest / "summary.json").read_text())
        print(f"summary:        action={summary['action']} counts={summary['counts']}")
    return 0


def cmd_abort(args: argparse.Namespace) -> int:
    """End every process this run launched, cooperatively first. The receipts remain."""
    from operator_driver.processes import alive, cancel_acp, owned_processes, terminate

    dest = Path(args.dest).resolve()
    stopped = 0
    for path in sorted((dest / "processes").glob("*.json")):
        if path.name.endswith(".exit.json"):
            continue
        receipt = json.loads(path.read_text())
        if alive(receipt):
            cancel_acp(receipt)
            stopped += 1
            print(f"stopped {path.stem} (pid {receipt['pid']})")
    for survivor in owned_processes(dest, all_commands=True):
        terminate(survivor)
        stopped += 1
        print(f"stopped stray pid {survivor['pid']}: {survivor['command'][:80]}")
    print(f"{stopped} process(es) stopped; receipts and stage products are untouched")
    return 0


def cmd_ledger(args: argparse.Namespace) -> int:
    path = Path(args.path) if args.path else ledger_mod.path(Path.cwd())
    rows = ledger_mod.read(path)
    if args.fate:
        finding, fate = args.fate
        ledger_mod.record_fate(path, args.run or "unknown", finding, fate, args.note or "")
        print(f"recorded {finding} -> {fate}")
        return 0
    report = ledger_mod.precision(rows)
    print(f"{path}: {report['findings']} findings, {report['with_fate']} with a recorded fate\n")
    print(f"{'lens/model':46} {'found':>6} {'conf':>6} {'post':>6} {'acted':>6} {'prec':>6}")
    for key, bucket in report["buckets"].items():
        precision = "-" if bucket["precision"] is None else f"{bucket['precision']:.2f}"
        print(
            f"{key:46} {bucket['found']:6} {bucket['confirmed']:6} {bucket['posted']:6} "
            f"{bucket['acted']:6} {precision:>6}"
        )
    return 0


def cmd_batch(args: argparse.Namespace) -> int:
    root = Path(args.dest).resolve()
    root.mkdir(parents=True, exist_ok=True)
    argv = [
        "gh",
        "pr",
        "list",
        "--label",
        args.label,
        "--json",
        "number,title,isDraft",
        "--limit",
        str(args.limit),
    ]
    if args.repo:
        argv += ["-R", args.repo]
    code, out, err = command(argv, Path.cwd(), timeout=180)
    if code:
        raise Park(f"gh pr list failed: {err.decode(errors='replace')[-500:]}")
    listed = [row for row in json.loads(out) if not row["isDraft"]]
    print(f"{len(listed)} open pull request(s) labelled {args.label!r}\n")
    results = []
    for row in listed:
        started = time.monotonic()
        dest = root / f"pr-{row['number']}"
        namespace = argparse.Namespace(
            **{
                **vars(args),
                "dest": str(dest),
                "pr": row["number"],
                "source": "gh",
                "facts": None,
                "repo_path": args.repo_path,
                "gate_cmd": args.gate_cmd,
                "rules": args.rules,
                "test_cmd": None,
                "sandbox_image": None,
            }
        )
        try:
            if cmd_setup(namespace) == 2:
                results.append({"number": row["number"], "status": "fast-path", "wall_s": 0})
                continue
            cmd_run(namespace)
            summary = json.loads((dest / "summary.json").read_text())
            capture = summary["evidence"].get("capture") or {}
            results.append(
                {
                    "number": row["number"],
                    "status": summary["action"],
                    "wall_s": round(time.monotonic() - started, 1),
                    "usage_usd": (capture.get("usage_totals") or {}).get("usd_list_price"),
                    "counts": summary["counts"],
                }
            )
        except Park as exc:
            results.append(
                {
                    "number": row["number"],
                    "status": "parked",
                    "reason": str(exc),
                    "wall_s": round(time.monotonic() - started, 1),
                }
            )
    (root / "batch.json").write_text(json.dumps(results, indent=2) + "\n")
    # "list-price" and never "spent": a pond-derived equivalent on subscription lanes.
    print(f"\n{'pr':>6} {'status':24} {'wall':>8} {'list-price':>11}")
    for row in results:
        status = str(row["status"])[:24]
        wall = float(row.get("wall_s") or 0)
        usage = row.get("usage_usd")
        priced = f"{usage:11.2f}" if isinstance(usage, (int, float)) else f"{'-':>11}"
        print(f"{row['number']:6} {status:24} {wall:8.1f} {priced}")
    print(f"\nbatch summary: {root}/batch.json")
    return 0


def main() -> int:
    # Shared flags live on every subcommand rather than only before it: a global-only
    # flag is the shape that makes `review-pr ready --no-pond` fail for no good reason.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--stages", help="an alternative stage template")
    common.add_argument(
        "--tier", choices=("container", "userns", "none"), help="override the sandbox tier"
    )
    common.add_argument(
        "--no-pond", action="store_true", help="run without capturing executor sessions into pond"
    )
    parser = argparse.ArgumentParser(prog="review-pr", description=__doc__, parents=[common])
    sub = parser.add_subparsers(dest="subcommand", required=True)

    ready = sub.add_parser("ready", parents=[common], help="check everything a paid review needs")
    ready.add_argument("--dest", help="a review workspace to check as well")
    ready.set_defaults(func=cmd_ready)

    setup = sub.add_parser(
        "setup", parents=[common], help="materialise a review workspace for one pull request"
    )
    setup.add_argument("--dest", required=True)
    setup.add_argument("--pr", type=int)
    setup.add_argument("--repo", "-R")
    setup.add_argument("--repo-path")
    setup.add_argument("--source", choices=("gh", "file"), default="gh")
    setup.add_argument("--facts", help="a PR descriptor, for --source file")
    setup.add_argument("--gate-cmd", help="override the base-derived validation command")
    setup.add_argument("--test-cmd", help="the command the tests-fail-on-base check runs")
    setup.add_argument("--rules", help="rule set for stage 0 (default: per repository)")
    setup.add_argument("--sandbox-image")
    setup.add_argument(
        "--force", action="store_true", help="review a diff below the fast-path floor anyway"
    )
    setup.set_defaults(func=cmd_setup)

    lint = sub.add_parser(
        "lint", parents=[common], help="stage 0 alone: the mechanical house rules"
    )
    lint.add_argument("--dest", required=True)
    lint.set_defaults(func=cmd_lint)

    gate = sub.add_parser(
        "gate", parents=[common], help="stage 1 alone: the base-pinned validation command"
    )
    gate.add_argument("--dest", required=True)
    gate.set_defaults(func=cmd_gate)

    run = sub.add_parser("run", parents=[common], help="run stages 0 to 4 and stop before posting")
    run.add_argument("--dest", required=True)
    run.add_argument("--run-id")
    run.add_argument("--skip-ready", action="store_true")
    run.set_defaults(func=cmd_run)

    post = sub.add_parser(
        "post", parents=[common], help="re-check state, then post the assembled review"
    )
    post.add_argument("--dest", required=True)
    post.add_argument("--confirm", required=True, choices=verdictcalc.ACTIONS)
    post.set_defaults(func=cmd_post)

    status = sub.add_parser(
        "status", parents=[common], help="what a run has durably finished, from disk alone"
    )
    status.add_argument("--dest", required=True)
    status.set_defaults(func=cmd_status)

    abort = sub.add_parser(
        "abort", parents=[common], help="end every process a run launched; receipts remain"
    )
    abort.add_argument("--dest", required=True)
    abort.set_defaults(func=cmd_abort)

    led = sub.add_parser("ledger", parents=[common], help="measured precision per lens and model")
    led.add_argument("--path")
    led.add_argument("--run")
    led.add_argument("--fate", nargs=2, metavar=("FINDING", "FATE"))
    led.add_argument("--note")
    led.set_defaults(func=cmd_ledger)

    batch = sub.add_parser(
        "batch", parents=[common], help="review every open pull request carrying a label"
    )
    batch.add_argument("--dest", required=True)
    batch.add_argument("--label", required=True)
    batch.add_argument("--repo", "-R")
    batch.add_argument("--repo-path")
    batch.add_argument("--gate-cmd")
    batch.add_argument("--rules")
    batch.add_argument("--limit", type=int, default=20)
    batch.add_argument("--force", action="store_true")
    batch.add_argument("--run-id")
    batch.add_argument("--skip-ready", action="store_true")
    batch.set_defaults(func=cmd_batch)

    args = parser.parse_args()
    try:
        return int(args.func(args))
    except Park as exc:
        sys.stderr.write(f"parked: {exc}\n")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())

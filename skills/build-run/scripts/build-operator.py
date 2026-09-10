#!/usr/bin/env python3
"""Readiness, execution and recovery for one frozen Bernstein phase build.

The filename deliberately avoids shadowing Python's stdlib operator module.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from operator_driver.driver import run_build
from operator_driver.readiness import check, freeze
from operator_driver.spec import Build
from operator_driver.storage import Ledger, Park, driver_lock


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("ready", "run", "resume", "status"))
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    root, plan = args.root.resolve(), args.plan.resolve()
    os.chdir(root)
    ledger = None
    try:
        build = Build(root, plan)
        ledger = Ledger(build.run_dir)
        if args.command == "status":
            latest = ledger.events[-1] if ledger.events else {}
            print(
                json.dumps(
                    {
                        "build": build.slug,
                        "event": latest.get("event", "not-started"),
                        "completed": ledger.last("build_completed") is not None,
                        "parked": ledger.last("parked"),
                        "ledger": str(ledger.path),
                    },
                    indent=2,
                )
            )
            return 0
        with driver_lock(root):
            ledger = Ledger(build.run_dir)
            if args.command == "ready":
                receipt = check(build)
                print(json.dumps(receipt, indent=2))
                return 0
            if args.command == "resume" and not ledger.last("build_started"):
                raise Park("no admitted build exists to resume")
            try:
                freeze(build, ledger)
                result = run_build(build, ledger)
            except Park as exc:
                if ledger.last("build_started") and not ledger.last("parked"):
                    ledger.append("parked", reason=str(exc))
                raise
            print(
                json.dumps(
                    {
                        "build": build.slug,
                        "status": "completed",
                        "tip": result["tip"],
                        "ledger": str(ledger.path),
                    },
                    indent=2,
                )
            )
            return 0
    except Park as exc:
        print(f"PARK: {exc}")
        return 2
    except KeyboardInterrupt:
        print("Interrupted; run resume to reconcile the recorded attempt.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())

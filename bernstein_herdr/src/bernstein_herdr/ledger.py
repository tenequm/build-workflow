"""Run-directory writers: runs.jsonl rows (append-only) and ledger.md lines."""

from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path


def now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def note(run_dir: Path, line: str) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    with (run_dir / "ledger.md").open("a") as f:
        f.write(f"- {now()} {line}\n")


def row(run_dir: Path, data: dict) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    with (run_dir / "runs.jsonl").open("a") as f:
        f.write(json.dumps({"ts": now(), **data}, separators=(",", ":")) + "\n")


def diff_stats(wt: Path, base: str) -> dict:
    subprocess.run(["git", "add", "-A", "-N", "."], cwd=wt, capture_output=True, check=False)
    numstat = subprocess.run(["git", "diff", base, "--numstat", "--", ".", ":!.agents"], cwd=wt, capture_output=True, text=True, check=False).stdout
    subprocess.run(["git", "reset", "-q"], cwd=wt, capture_output=True, check=False)
    ca = cd = ta = td = n = 0
    for line in numstat.splitlines():
        p = line.split("\t")
        if len(p) < 3 or not p[0].isdigit():
            continue
        n += 1
        if re.search(r"_test\.go$|testdata/|\.test\.ts$|\.spec\.ts$", p[2]):
            ta += int(p[0]); td += int(p[1])
        else:
            ca += int(p[0]); cd += int(p[1])
    return {"files": n, "code_add": ca, "code_del": cd, "test_add": ta, "test_del": td}


def archive(wt: Path, base: str, dest: Path) -> dict:
    dest.mkdir(parents=True, exist_ok=True)
    run = lambda *a: subprocess.run(a, cwd=wt, capture_output=True, text=True, check=False).stdout
    run("git", "add", "-A", "-N", ".")
    (dest / "diff.patch").write_text(run("git", "diff", base, "--", ".", ":!.agents"))
    (dest / "numstat.txt").write_text(run("git", "diff", base, "--numstat", "--", ".", ":!.agents"))
    (dest / "status.txt").write_text(run("git", "status", "--porcelain"))
    run("git", "reset", "-q")
    return diff_stats(wt, base)


def report_claims(report: Path) -> dict:
    """Exit codes and issue counts the executor claimed in its report's Validation section."""
    if not report.exists():
        return {"present": False}
    text = report.read_text()
    exits = [int(x) for x in re.findall(r"[Ee]xit(?: code)?[:=]?\s*(\d+)", text)]
    issues = [int(x) for x in re.findall(r"(\d+) issues?\.", text)]
    deviations_none = bool(re.search(r"##\s*Deviations\s*\n+\s*(none|None|-\s*none)", text))
    return {"present": True, "claimed_exit_codes": exits, "claimed_issue_counts": issues, "deviations_none": deviations_none,
            "mentions_lint": bool(re.search(r"golangci|lint", text, re.I))}

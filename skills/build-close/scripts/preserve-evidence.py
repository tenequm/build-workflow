#!/usr/bin/env python3
"""Verify completion, preserve immutable evidence and Git objects before cleanup."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def git(root, *args):
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=True, timeout=120
    ).stdout.strip()


def inside(root, rel):
    path = root / rel
    if (
        Path(rel).is_absolute()
        or ".." in Path(rel).parts
        or path.is_symlink()
        or not path.resolve().is_relative_to(root.resolve())
    ):
        raise ValueError(f"unsafe evidence path: {rel}")
    return path


def verify(run: Path) -> tuple[dict, set[str]]:
    raw = (run / "workflow.jsonl").read_bytes()
    if not raw.endswith(b"\n"):
        raise ValueError("torn workflow journal")
    previous = "0" * 64
    completed = None
    objects = set()
    phases, accepted = 0, set()
    for index, line in enumerate(raw.splitlines()):
        row = json.loads(line)
        seal = row.pop("hash")
        if row["seq"] != index or row["previous"] != previous or sha(canonical(row)) != seal:
            raise ValueError("workflow journal chain differs")
        previous = seal
        if row["event"] == "parked":
            raise ValueError("parked builds cannot be cleaned up as completed")
        if row["event"] == "native_closed":
            native = inside(run, "native/" + row["run_id"])
            manifest = json.loads((native / "archive.json").read_text())
            for rel, expected in manifest.items():
                if sha(inside(native, rel).read_bytes()) != expected:
                    raise ValueError("native evidence changed")
            for proof in row["proofs"]:
                scorer = inside(run, proof["scorer_receipt"])
                if sha(scorer.read_bytes()) != proof["scorer_receipt_sha256"]:
                    raise ValueError("scorer receipt changed")
                objects.update((proof["head"], proof["merge_commit"]))
        if row["event"] == "judge_receipt":
            dest = inside(run, "judge/" + row["operation"])
            receipt = json.loads((dest / "receipt.json").read_text())
            if sha(canonical(receipt)) != row["receipt_hash"]:
                raise ValueError("judge receipt changed")
            for rel, expected in receipt["artifacts"].items():
                if sha(inside(dest, rel).read_bytes()) != expected:
                    raise ValueError("judge evidence changed")
            objects.update((receipt["base"], receipt["tip"], receipt["staged"]))
        if row["event"] == "phase_accepted":
            accepted.add(row["phase"])
        if row["event"] == "build_completed":
            completed, phases = row, row["phases"]
            objects.update((row["base"], row["tip"]))
    if completed is None or len(accepted) != phases:
        raise ValueError("build lacks complete accepted-phase evidence")
    for receipt_path in (run / "reports").glob("*/*/receipt.json"):
        receipt = json.loads(receipt_path.read_text())
        if receipt.get("head"):
            objects.add(receipt["head"])
    return completed, objects


def preserve(root: Path, run: Path, dest: Path) -> dict:
    if dest == run or dest.is_relative_to(run) or run.is_relative_to(dest):
        raise ValueError("evidence destination must be separate from the source")
    completed, objects = verify(run)
    git(root, "merge-base", "--is-ancestor", completed["tip"], "HEAD")
    # report.md may be regenerated after validation, but code may not change.
    plans = list((root / ".agents/build/plans").glob("*.steps.yaml"))
    import yaml

    sidecars = [
        yaml.safe_load(path.read_text())
        for path in plans
        if path.stem.removesuffix(".steps") == run.name
    ]
    if len(sidecars) != 1:
        raise ValueError("cannot resolve completed build sidecar")
    report = (Path(sidecars[0]["defaults"]["doc"]).parent / "report.md").as_posix()
    if set(git(root, "diff", "--name-only", completed["tip"], "HEAD").splitlines()) - {report}:
        raise ValueError("code changed after the validated build tip")
    if git(root, "diff", "--name-only", "HEAD"):
        raise ValueError("workspace has uncommitted tracked changes")
    for path in run.rglob("*"):
        if path.is_symlink() or (
            path.is_dir() and path.name == "worktree" and (path / ".git").exists()
        ):
            raise ValueError(
                "remove closed ceremony worktrees before archival; preserve parked evidence in place"
            )
    # Keep reviewed/scored commits reachable after native graveyard cleanup and
    # branch deletion, and include portable objects in the evidence archive.
    refs = []
    for commit in sorted(objects):
        if len(commit) != 40 or any(c not in "0123456789abcdef" for c in commit):
            raise ValueError("invalid archived commit identity")
        ref = f"refs/build/evidence/{run.name}/{commit}"
        existing = subprocess.run(
            ["git", "rev-parse", "--verify", ref], cwd=root, capture_output=True, text=True
        )
        if existing.returncode:
            git(root, "update-ref", ref, commit, "0" * 40)
        elif existing.stdout.strip() != commit:
            raise ValueError("evidence ref moved")
        refs.append(ref)
    bundle = run / "objects.bundle"
    if not bundle.exists():
        temporary = run / "objects.bundle.partial"
        git(root, "bundle", "create", str(temporary), *refs)
        temporary.replace(bundle)
    git(root, "bundle", "verify", str(bundle))
    manifest = {
        path.relative_to(run).as_posix(): sha(path.read_bytes())
        for path in run.rglob("*")
        if path.is_file()
    }
    # Refuse divergent existing immutable artifacts; mutable human handoff/index
    # files may be refreshed by a repeated pre-cleanup copy.
    for rel, expected in manifest.items():
        target = inside(dest, rel)
        if (
            target.exists()
            and rel.startswith(("native/", "judge/", "reports/", "readiness/"))
            and sha(target.read_bytes()) != expected
        ):
            raise ValueError("destination contains conflicting immutable evidence")
    shutil.copytree(run, dest, dirs_exist_ok=True)
    for rel, expected in manifest.items():
        if sha(inside(dest, rel).read_bytes()) != expected:
            raise ValueError("evidence copy failed verification")
    (dest / "preservation.json").write_bytes(
        canonical({"tip": completed["tip"], "files": manifest})
    )
    return {"tip": completed["tip"], "files": len(manifest), "destination": str(dest)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--dest", type=Path, required=True)
    args = parser.parse_args()
    print(
        json.dumps(preserve(args.root.resolve(), args.run.resolve(), args.dest.resolve()), indent=2)
    )

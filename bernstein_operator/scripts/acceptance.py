"""Run contracts against a private source copy carrying the three cutover patches."""

from __future__ import annotations

import os
import runpy
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import bernstein


def main() -> int:
    package = Path(__file__).resolve().parents[1]
    scripts = package.parent / "skills/build-run/scripts"
    prepare = runpy.run_path(str(scripts / "prepare-engine.py"))["prepare"]
    with tempfile.TemporaryDirectory(prefix="operator-engine-") as tmp:
        source = Path(tmp) / "src"
        shutil.copytree(
            Path(bernstein.__file__).parent,
            source / "bernstein",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        prepare(Path(tmp))
        prepare(Path(tmp), check=True)
        env = {
            **os.environ,
            "PYTHONPATH": str(source) + os.pathsep + str(scripts),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        return subprocess.run(
            [sys.executable, "-m", "pytest", str(package / "tests"), *sys.argv[1:]],
            cwd=package,
            env=env,
            check=False,
        ).returncode


if __name__ == "__main__":
    raise SystemExit(main())

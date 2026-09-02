"""Gate: a fresh blind judge in its own worktree; fails on any certain defect without a reproducing test.

Stages <worktree>/../judge-<task>/W with the task diff applied and staged, copies the
brief and templates/judge-prompt.md, spawns the judge through the herdr adapter
(kind from BUILD_JUDGE_KIND, default claude; model BUILD_JUDGE_MODEL, default
claude-opus-5), waits for blind-review.md, parses the Verdict section.
Judge family rule: never weaker than the executor; Codex and Flash never judge Opus.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from bernstein.core.quality.gate_plugins import GatePlugin
from bernstein.core.quality.gate_runner import GateResult

CERTAIN = re.compile(r"\bcertain\b", re.I)


class BlindJudgeGate(GatePlugin):
    @property
    def name(self) -> str:
        return "blind_judge"

    @property
    def required(self) -> bool:
        return os.environ.get("BUILD_JUDGE_REQUIRED", "1") == "1"

    @property
    def condition(self) -> str:
        return "any_changed"

    def run(self, changed_files: list[str], run_dir: Path, task_title: str, task_description: str) -> GateResult:
        from bernstein_herdr.adapter import HerdrClaudeAdapter

        base = os.environ.get("BUILD_BASE_REF", "HEAD~1")
        judge_dir = run_dir.parent / f"judge-{run_dir.name}"
        wt = judge_dir / "W"
        judge_dir.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "worktree", "add", "--detach", str(wt), base], cwd=run_dir, check=True, capture_output=True)
        patch = subprocess.run(["git", "diff", base, "--", ".", ":!.agents"], cwd=run_dir, capture_output=True, text=True, check=True).stdout
        (judge_dir / "W.patch").write_text(patch)
        subprocess.run(["git", "apply", "--index", "../W.patch"], cwd=wt, check=True, capture_output=True)
        brief = run_dir / os.environ.get("BUILD_BRIEF_RELPATH", ".agents/briefs/brief.md")
        if brief.exists():
            (judge_dir / "brief.md").write_text(brief.read_text())
        prompt = (Path(__file__).resolve().parents[3] / "templates" / "judge-prompt.md").read_text().replace("<judge dir>", str(judge_dir))
        (judge_dir / "judge-prompt.md").write_text(prompt)

        os.environ["BUILD_REPORT_RELPATH"] = "blind-review.md"
        os.environ["BUILD_BRIEF_RELPATH"] = "judge-prompt.md"
        adapter = HerdrClaudeAdapter()

        class _Model:
            model = os.environ.get("BUILD_JUDGE_MODEL", "claude-opus-5")

        result = adapter.spawn(prompt=prompt, workdir=judge_dir, model_config=_Model(), session_id=f"judge-{run_dir.name}")
        result.proc.wait()
        review = (judge_dir / "blind-review.md").read_text() if (judge_dir / "blind-review.md").exists() else ""
        verdict = review.split("Verdict", 1)[-1] if "Verdict" in review else review
        certain = len(CERTAIN.findall(verdict))
        blocked = bool(review) and ("do not merge" in verdict.lower() or certain > 0)
        details = json.dumps({"judge_dir": str(judge_dir), "certain_mentions": certain, "review_present": bool(review)})
        return GateResult(name=self.name, status="fail" if blocked else "pass", required=self.required, blocked=blocked and self.required,
                          cached=False, duration_ms=0, details=details)

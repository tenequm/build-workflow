"""Plan, sidecar and run-directory resolution shared by the adapter, gates and CLI.

Bernstein's plan schema is strict (additionalProperties false), so build-workflow
options per step live in a sidecar next to the plan: `<slug>.steps.yaml`, keyed by
step title. Both files are tracked under `.agents/build/plans/`; the run directory
`.agents/build/runs/<slug>/` is untracked and lives at the repo root, never in a
worktree.

Sidecar shape:
    defaults: {base: <ref>, shadow: null, judge: required|optional|none}
    steps:
      "<step title>": {brief: briefs/<step>.md, report: .agents/<step>.md, base: <ref>,
                       shadow: agy|null, judges: "<phase title>", judge: required|optional|none}
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import yaml

TASK_LINE = re.compile(r"^### Task \d+: (.+?) \(id=", re.M)


def repo_root(start: Path | None = None) -> Path:
    out = subprocess.run(["git", "rev-parse", "--git-common-dir"], cwd=start or Path.cwd(), capture_output=True, text=True, check=True).stdout.strip()
    return Path(out).resolve().parent


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else ""


@dataclass
class Step:
    title: str
    slug: str
    files: list[str]
    brief: Path
    report_rel: str
    base: str
    shadow: str | None
    judges: str | None
    judge: str
    run_dir: Path
    plan_path: Path
    raw: dict = field(default_factory=dict)


@dataclass
class Plan:
    path: Path
    slug: str
    root: Path
    data: dict
    sidecar: dict

    @property
    def run_dir(self) -> Path:
        return self.root / ".agents" / "build" / "runs" / self.slug

    def steps(self) -> list[dict]:
        return [s for st in self.data.get("stages", []) for s in st.get("steps", [])]

    def step(self, title: str) -> Step:
        raw = next((s for s in self.steps() if s.get("title") == title), None)
        if raw is None:
            raise KeyError(f"step not in plan: {title!r}")
        d = self.sidecar.get("defaults", {})
        s = self.sidecar.get("steps", {}).get(title, {})
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:48]
        return Step(
            title=title, slug=slug, files=list(raw.get("files") or []),
            brief=self.run_dir / s.get("brief", f"briefs/{slug}.md"),
            report_rel=s.get("report", f".agents/{slug}.md"),
            base=s.get("base", d.get("base", "HEAD~1")),
            shadow=s.get("shadow", d.get("shadow")),
            judges=s.get("judges"), judge=s.get("judge", d.get("judge", "optional")),
            run_dir=self.run_dir, plan_path=self.path, raw=raw,
        )

    def step_from_prompt(self, prompt: str) -> Step:
        m = TASK_LINE.search(prompt)
        if m:
            return self.step(m.group(1).strip())
        for s in self.steps():
            if s.get("title") and s["title"] in prompt:
                return self.step(s["title"])
        raise KeyError("no plan step title found in prompt")


def load_plan(path: Path | None = None, root: Path | None = None) -> Plan:
    root = root or repo_root()
    if path is None:
        plans = sorted((root / ".agents" / "build" / "plans").glob("*.yaml"))
        plans = [p for p in plans if not p.name.endswith(".steps.yaml")]
        if len(plans) != 1:
            raise RuntimeError(f"expected one plan under .agents/build/plans, found {len(plans)}; pass --plan")
        path = plans[0]
    data = yaml.safe_load(path.read_text()) or {}
    sidecar_path = path.with_name(path.name.removesuffix(".yaml") + ".steps.yaml")
    sidecar = yaml.safe_load(sidecar_path.read_text()) if sidecar_path.exists() else {}
    return Plan(path=path, slug=data.get("name", path.stem), root=root, data=data, sidecar=sidecar or {})


def pinned_hashes(plan: Plan) -> dict[str, str]:
    h = {"spec": sha256(plan.root / "docs" / "spec.md"), "plan": sha256(plan.path)}
    for s in plan.steps():
        st = plan.step(s["title"])
        h[f"brief:{st.slug}"] = sha256(st.brief)
    return h

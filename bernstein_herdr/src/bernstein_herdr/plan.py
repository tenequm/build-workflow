"""Plan, sidecar and run-directory resolution shared by the adapter, gates and CLI.

Bernstein's plan schema is strict (additionalProperties false), so build-workflow
options per step live in a sidecar next to the plan: `<slug>.steps.yaml`, keyed by
step title. Both files are tracked under `.agents/build/plans/`; the run directory
`.agents/build/runs/<slug>/` is untracked and lives at the repo root, never in a
worktree.

Sidecar shape:
    defaults: {base: <ref>, doc: <plan dir>/plan.md, spec: <plan dir>/spec.md,
               design: <product spec>, gate_cmd: just check,
               shadow: null, judge: required|optional|none}
    steps:
      "<step title>": {brief: briefs/<step>.md, report: .agents/<step>.md, base: <ref>,
                       gate_cmd: <command>, shadow: null,
                       judges: "<phase title>", fixes: "<phase title>",
                       judge: required|optional|none}

Dispatch is `role:` + `role_model_policy` in bernstein.yaml; a sidecar `cli` is legacy
and not read by anything that survives a retry.
"""

from __future__ import annotations

import hashlib
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

import yaml

TASK_LINE = re.compile(r"^### Task \d+: (.+?) \(id=", re.M)
# Bernstein's own adapters read the task id out of the prompt the same way
# (adapters/manager.py:51); it is the only channel that carries it to a spawn.
TASK_ID = re.compile(r"\(id=([^)]+)\)")


def repo_root(start: Path | None = None) -> Path:
    """The root of the plan this path belongs to.

    The nearest enclosing directory that holds `.agents/build/plans` wins, because the
    design's unit is one plan per repo root and a second concurrent plan gets its own
    TOP-LEVEL worktree. `--git-common-dir` cannot see that: from inside any linked
    worktree it points at the main checkout, so a plan root that is itself a worktree
    (and every Bernstein worktree it spawns) resolved to the wrong repository. The
    common dir stays as the fallback for a path with no plan above it.

    Candidates under a `.sdd` or `.agents` directory are skipped. The plan is tracked, so
    an executor worktree at `<root>/.sdd/worktrees/<id>` carries its own committed copy;
    without the skip a step resolved to that copy and, on an uncommitted plan edit, died
    with "step not in plan".
    """
    base = Path(start or Path.cwd()).resolve()
    for d in (base, *base.parents):
        if {".sdd", ".agents"} & set(d.parts):
            continue
        if (d / ".agents" / "build" / "plans").is_dir():
            return d
    out = subprocess.run(["git", "rev-parse", "--git-common-dir"], cwd=base, capture_output=True, text=True, check=True).stdout.strip()
    git_dir = Path(out)
    return (git_dir if git_dir.is_absolute() else base / git_dir).resolve().parent


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
    gate_cmd: str
    shadow: str | None
    judges: str | None
    fixes: str | None
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

    def _brief_path(self, rel: str) -> Path:
        """Run-dir relative by default; repo-root relative when it starts with `.agents/`.

        A brief the executor must read has to be TRACKED, because the only tree the agent
        can see is its worktree and the run directory is untracked and lives at the root.
        Tracked briefs sit at `.agents/build/plans/<slug>/<step>.md`, so a sidecar value
        that already starts at `.agents/` is resolved against the repo root; anything else
        keeps the old run-dir meaning.
        """
        return (self.root / rel) if rel.startswith(".agents/") else (self.run_dir / rel)

    def step(self, title: str) -> Step:
        raw = next((s for s in self.steps() if s.get("title") == title), None)
        if raw is None:
            raise KeyError(f"step not in plan: {title!r}")
        d = self.sidecar.get("defaults", {})
        s = self.sidecar.get("steps", {}).get(title, {})
        slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:48]
        return Step(
            title=title, slug=slug, files=list(raw.get("files") or []),
            brief=self._brief_path(s.get("brief", f"briefs/{slug}.md")),
            report_rel=s.get("report", f".agents/{slug}.md"),
            base=s.get("base", d.get("base", "HEAD~1")),
            # Per-step, falling back to the sidecar default. A plan whose later phase
            # leaves a module red drags every earlier phase's gate down to the
            # intersection of what all of them can pass when one command serves them all
            # (measured 2026-09-02); a step whose own scope is green gets its own command.
            gate_cmd=s.get("gate_cmd", d.get("gate_cmd", "just check")),
            shadow=s.get("shadow", d.get("shadow")),
            judges=s.get("judges"),
            # Read by readiness only: a fix step must carry the SCOPED gate command of the
            # step it fixes, not the whole-tree default a later phase leaves red.
            fixes=s.get("fixes"),
            judge=s.get("judge", d.get("judge", "optional")),
            run_dir=self.run_dir, plan_path=self.path, raw=raw,
        )

    def task_id_from_prompt(self, prompt: str) -> str:
        m = TASK_ID.search(prompt)
        return m.group(1) if m else ""

    def step_from_prompt(self, prompt: str) -> Step:
        m = TASK_LINE.search(prompt)
        if m:
            return self.step(m.group(1).strip())
        for s in self.steps():
            if s.get("title") and s["title"] in prompt:
                return self.step(s["title"])
        raise KeyError("no plan step title found in prompt")


def active_plan_name(root: Path) -> str | None:
    """Return the plan file named by ACTIVE, or None when ACTIVE is absent."""
    active = root / ".agents" / "build" / "plans" / "ACTIVE"
    if not active.exists():
        return None
    raw = active.read_text()
    lines = raw.splitlines()
    if len(lines) != 1 or not lines[0] or lines[0] != lines[0].strip():
        raise RuntimeError(f"invalid {active}: expected one bare <slug>.yaml file name")
    name = lines[0]
    if (Path(name).name != name or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*\.yaml", name)
            or name.endswith(".steps.yaml")):
        raise RuntimeError(f"invalid {active}: expected one bare <slug>.yaml file name, got {name!r}")
    return name


def load_plan(path: Path | None = None, root: Path | None = None) -> Plan:
    root = root or repo_root()
    if path is None:
        name = active_plan_name(root)
        if name is not None:
            path = root / ".agents" / "build" / "plans" / name
            if not path.is_file():
                raise RuntimeError(f"ACTIVE names missing plan file {path}")
        else:
            plans = sorted((root / ".agents" / "build" / "plans").glob("*.yaml"))
            plans = [p for p in plans if not p.name.endswith(".steps.yaml")]
            if len(plans) != 1:
                raise RuntimeError(
                    f"expected one plan under .agents/build/plans, found {len(plans)}; pass --plan "
                    "or write the plan file name to .agents/build/plans/ACTIVE"
                )
            path = plans[0]
    data = yaml.safe_load(path.read_text()) or {}
    sidecar_path = path.with_name(path.name.removesuffix(".yaml") + ".steps.yaml")
    sidecar = yaml.safe_load(sidecar_path.read_text()) if sidecar_path.exists() else {}
    return Plan(path=path, slug=data.get("name", path.stem), root=root, data=data, sidecar=sidecar or {})


def pinned_hashes(plan: Plan) -> dict[str, str]:
    defaults = plan.sidecar.get("defaults", {})
    doc = defaults.get("doc")
    spec_path = plan.root / doc if doc else plan.root / "docs" / "spec.md"
    h = {"spec": sha256(spec_path), "plan": sha256(plan.path)}
    build_spec = defaults.get("spec")
    if build_spec:
        h["build_spec"] = sha256(plan.root / build_spec)
    for s in plan.steps():
        st = plan.step(s["title"])
        h[f"brief:{st.slug}"] = sha256(st.brief)
    return h

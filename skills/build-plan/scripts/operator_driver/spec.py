"""Compile the authored plan into phase-local POST payloads without helper losses."""

from __future__ import annotations

import fnmatch
import math
import re
import subprocess
from pathlib import Path

import yaml
from bernstein.core.planning.plan_loader import load_plan
from bernstein.core.server.server_models import TaskCreate

from .storage import Park, canonical, contained, digest


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise Park(f"git {args[0]}: {result.stderr[-1000:]}")
    return result.stdout.strip()


class Build:
    def __init__(self, root: Path, plan: Path):
        self.root = root.resolve()
        self.path = plan.resolve()
        self.rel = self.path.relative_to(self.root).as_posix()
        self.data = yaml.safe_load(self.path.read_text())
        self.sidecar_path = self.path.with_suffix(".steps.yaml")
        self.sidecar = yaml.safe_load(self.sidecar_path.read_text())
        self.seed = yaml.safe_load((root / "bernstein.yaml").read_text())
        self.slug = self.data["name"]
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]*", self.slug):
            raise Park("build name must be a safe path/ref component")
        self.run_dir = contained(root, f".agents/build/runs/{self.slug}")
        self.branch = git(root, "symbolic-ref", "--short", "HEAD")
        if self.branch in {"main", "master"} or self.branch.startswith(
            ("agent/", "salvage/", "spec/")
        ):
            raise Park("build root must be an isolated integration branch")
        if self.seed["quality_gates"]["base_ref"] != self.branch:
            raise Park("quality gate base_ref differs from integration branch")
        self.phases = self.sidecar.get("phases", [])
        if not self.phases:
            raise Park("sidecar has no explicit phase boundaries")
        self.config, loaded = load_plan(self.path)
        self.tasks = {task.title: task for task in loaded}
        seen_stages = set()
        for stage in self.data["stages"]:
            if stage["name"] in seen_stages or not set(stage.get("depends_on", [])) <= seen_stages:
                raise Park(
                    "stages must have unique names and dependencies on earlier declared stages"
                )
            seen_stages.add(stage["name"])
        if self.config.repos:
            raise Park("operator phase builds support one workspace repository")
        if self.config.max_agents and self.config.max_agents != self.seed.get("max_agents"):
            raise Park("plan max_agents differs from the native seed used at launch")
        self.raw = {step["title"]: step for stage in self.data["stages"] for step in stage["steps"]}
        if len(loaded) != len(self.tasks) or len(self.raw) != len(loaded):
            raise Park("task titles must be globally unique")
        self.bounds = self.sidecar["bounds"]
        for field in ("max_attempts", "max_wall_s", "max_spend_usd", "run_budget_usd"):
            if (
                isinstance(self.bounds.get(field), bool)
                or not isinstance(self.bounds.get(field), (int, float))
                or not math.isfinite(self.bounds[field])
                or self.bounds[field] <= 0
            ):
                raise Park(f"missing positive whole-build bound: {field}")
        owned = []
        self.pins = {
            self.rel: digest(self.path.read_bytes()),
            self.sidecar_path.relative_to(root).as_posix(): digest(self.sidecar_path.read_bytes()),
            "bernstein.yaml": digest((root / "bernstein.yaml").read_bytes()),
        }
        for phase in self.phases:
            if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]*", phase["name"]):
                raise Park("invalid phase name")
            titles = phase["steps"]
            if not titles or not phase.get("fix"):
                raise Park(
                    "each phase needs executor steps and a complete pinned fix specification"
                )
            owned.extend([*titles, phase["fix"]])
            judge = phase["judge"]
            transport = judge.get("transport", "claude")
            if transport not in ("claude", "acp"):
                raise Park("judge transport must be claude or acp")
            if (
                not isinstance(judge.get("adapter_argv"), list)
                or not judge["adapter_argv"]
                or not all(isinstance(v, str) and v for v in judge["adapter_argv"])
            ):
                raise Park("judge adapter_argv must name a pinned ACP adapter")
            if not isinstance(judge.get("model"), str) or not judge["model"]:
                raise Park("judge needs an explicit model")
            if type(judge.get("max_turns")) is not int or judge["max_turns"] <= 0:
                raise Park("judge needs a positive integer max_turns")
            if any(
                type(judge.get(key)) not in (int, float)
                or not math.isfinite(judge[key])
                or judge[key] <= 0
                for key in ("timeout_s", "budget_usd")
            ):
                raise Park("judge needs timeout_s and budget_usd bounds")
            self._pin(judge["brief"])
            roles = [self.raw[title]["role"] for title in titles]
            if len(roles) != len(set(roles)):
                raise Park("phase executor roles must be distinct to prevent batching")
        if len(owned) != len(set(owned)) or set(owned) != set(self.tasks):
            raise Park("every authored task must belong to exactly one phase or fix mini-run")
        if len({phase["name"] for phase in self.phases}) != len(self.phases):
            raise Park("duplicate phase names")
        placement = {
            title: index for index, phase in enumerate(self.phases) for title in phase["steps"]
        }
        fix_titles = {phase["fix"] for phase in self.phases}
        for index, phase in enumerate(self.phases):
            for title in [*phase["steps"], phase["fix"]]:
                for dep in self.tasks[title].depends_on:
                    predecessor = (
                        dep  # Native load_plan returns dependency TITLES, not provisional IDs.
                    )
                    if (
                        predecessor not in self.tasks
                        or predecessor in fix_titles
                        or placement.get(predecessor, index + 1) > index
                    ):
                        raise Park(
                            f"dependency is missing, conditional, or in a future phase: {title}"
                        )
        if self.phases[-1].get("final_regression") is not True:
            raise Park("last phase must declare final_regression: true with whole-tree validation")
        final = self.phases[-1]
        if len(final["steps"]) != 1:
            raise Park("final regression must be one executor over the combined prior-phase tree")
        whole = self.sidecar.get("defaults", {}).get("gate_cmd")
        if not whole or any(
            self.sidecar["steps"][title].get("gate_cmd", whole) != whole
            for title in [*final["steps"], final["fix"]]
        ):
            raise Park("final regression and its repair must run the whole-tree command")
        if type(self.bounds["max_attempts"]) is not int:
            raise Park("max_attempts must be an integer")
        for title, task in self.tasks.items():
            unsupported = {
                "repo",
                "depends_on_repo",
                "mode",
                "phases",
                "artifact_spec",
                "attachments",
            } & self.raw[title].keys()
            if unsupported:
                raise Park(f"unsupported executor declaration: {title}: {sorted(unsupported)}")
            dispatch = self.seed["role_model_policy"][task.role]
            if any(
                self.raw[title].get(key, dispatch[key]) != dispatch[key]
                for key in ("cli", "model", "effort")
            ):
                raise Park(f"step dispatch disagrees with its role policy: {title}")
            step = self.sidecar["steps"][title]
            self._pin(step["brief"])
            contained(root, step["report"])
            if not step.get("gate_cmd", self.sidecar.get("defaults", {}).get("gate_cmd")):
                raise Park(f"missing scorer command: {title}")
            if not task.owned_files:
                raise Park(f"missing files declaration: {title}")
            for pattern in task.owned_files:
                contained(root, pattern)
            declared = self.raw[title].get("completion_signals")
            signals = [
                {"type": signal.type, "value": signal.value} for signal in task.completion_signals
            ]
            if not declared or declared != signals:
                raise Park(f"declared and loaded completion signals differ: {title}")
            for signal in signals:
                if signal["type"] == "file_contains":
                    if " :: " not in signal["value"]:
                        raise Park(f"file_contains requires value: path :: needle: {title}")
                    contained(root, signal["value"].split(" :: ", 1)[0])
        for rel in (self.sidecar.get("defaults", {}).get(key) for key in ("doc", "spec", "design")):
            if rel:
                self._pin(rel)
        for rel in self.data.get("context_files", []):
            self._pin(rel)
        self.fingerprint = digest(canonical(self.pins))
        for phase in self.phases:
            self.payloads(phase["steps"], "readiness")
            self.payloads([phase["fix"]], "readiness")

    def _pin(self, rel: str):
        path = contained(self.root, rel)
        self.pins[rel] = digest(path.read_bytes())

    def verify_pins(self, base: str):
        for rel, expected in self.pins.items():
            current = contained(self.root, rel).read_bytes()
            frozen = subprocess.run(
                ["git", "show", f"{base}:{rel}"], cwd=self.root, capture_output=True, check=True
            ).stdout
            if digest(current) != expected or frozen != current:
                raise Park(f"frozen input drift: {rel}")

    def payloads(
        self, titles: list[str], run_id: str, fix_input: dict | None = None
    ) -> list[tuple[str, dict]]:
        result = []
        selected = set(titles)
        for title in titles:
            task = self.tasks[title]
            policy = self.seed["role_model_policy"][task.role]
            spec = self.sidecar["steps"][title]
            dependencies = [dep for dep in task.depends_on if dep in selected]
            description = task.description + f"\n\nAttempt identity: {run_id}."
            if self.config.constraints:
                description += "\n\nBuild constraints:\n" + "\n".join(self.config.constraints)
            attachments = list(self.data.get("context_files", []))
            if spec["brief"] not in attachments:
                attachments.append(spec["brief"])
            if fix_input:
                description += (
                    "\n\nImmutable review input (verify the SHA-256 before use):\n"
                    + canonical(fix_input).decode()
                )
            body: dict = {
                "title": title,
                "description": description,
                "role": task.role,
                "priority": task.priority,
                "owned_files": list(task.owned_files),
                "depends_on": [],
                "scope": task.scope.value,
                "complexity": task.complexity.value,
                "completion_signals": [
                    {"type": signal.type, "value": signal.value}
                    for signal in task.completion_signals
                ],
                "cli": policy["cli"],
                "model": policy["model"],
                "effort": policy["effort"],
                "metadata": {
                    "context_files": attachments,
                    "operator_run": run_id,
                    "operator_spec": self.fingerprint,
                    "operator_dependencies": dependencies,
                },
            }
            TaskCreate.model_validate(body)
            result.append((title, body))
        # Concrete dependency IDs are substituted only after each predecessor POST.
        ordered = []
        while result:
            ready = [
                (title, body)
                for title, body in result
                if set(body["metadata"]["operator_dependencies"]) <= {t for t, _ in ordered}
            ]
            if not ready:
                raise Park("phase dependencies contain a cycle")
            ordered.extend(ready)
            result = [item for item in result if item not in ready]
        return ordered

    def fix_scope_covers(self, phase: dict, evidence: list[dict]) -> bool:
        files = self.tasks[phase["fix"]].owned_files
        return all(
            any(fnmatch.fnmatchcase(item["file"], pattern) for pattern in files)
            for item in evidence
        )

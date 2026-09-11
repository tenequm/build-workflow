"""Load and validate the template plan. A stage never guesses what it was pinned to."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml
from operator_driver.storage import Park

TEMPLATES = Path(__file__).resolve().parents[2] / "templates"
LENS_ORDER = ("cleanliness", "design", "efficiency", "gating")
REPORT_CATEGORY_ORDER = ("correctness", "convention", "cleanliness", "design", "efficiency")


def template(name: str) -> str:
    path = TEMPLATES / name
    if not path.is_file():
        raise Park(f"this skill is missing its own template: {name}")
    return path.read_text()


def load(path: Path | None = None) -> dict[str, Any]:
    data = yaml.safe_load((path or TEMPLATES / "stages.yaml").read_text())
    if not isinstance(data, dict) or data.get("version") != 1:
        raise Park("stage template must be a version 1 mapping")
    families = data.get("families")
    if not isinstance(families, dict) or not families:
        raise Park("stage template declares no agent families")
    for name, family in families.items():
        if family.get("transport") not in ("claude", "acp"):
            raise Park(f"family {name} needs transport claude or acp")
        argv = family.get("adapter_argv")
        if (
            not isinstance(argv, list)
            or not argv
            or not all(isinstance(v, str) and v for v in argv)
        ):
            raise Park(f"family {name} needs a pinned adapter_argv")
        family["adapter_argv"] = [
            value.replace("{{HOME}}", os.path.expanduser("~")) for value in argv
        ]
    lenses = data.get("lenses")
    if not isinstance(lenses, dict) or set(lenses) != set(LENS_ORDER):
        raise Park(f"stage template must declare exactly the lenses {LENS_ORDER}")
    for name, lens in lenses.items():
        _bounds(f"lens {name}", lens)
        if lens["family"] not in families:
            raise Park(f"lens {name} routes to an undeclared family: {lens['family']}")
        forbidden = lens.get("forbid_families") or []
        if lens["family"] in forbidden:
            raise Park(f"lens {name} is pinned to a family its own brief forbids")
    roles = data.get("roles") or {}
    for name in ("verifier", "claims", "body"):
        if name not in roles:
            raise Park(f"stage template declares no {name} role")
    _bounds("role claims", roles["claims"])
    _bounds("role body", roles["body"])
    verifier = roles["verifier"]
    for key in ("budget_usd", "max_turns", "timeout_s"):
        if key not in verifier:
            raise Park(f"role verifier needs {key}")
    if not isinstance(verifier.get("models"), dict) or set(verifier["models"]) - set(families):
        raise Park("role verifier needs a model per declared family")
    routing = data.get("routing") or {}
    if set(routing.get("opposite") or {}) - set(families):
        raise Park("routing names an undeclared family")
    if set(routing.get("reroute_lenses") or []) - set(LENS_ORDER):
        raise Park("routing reroutes an unknown lens")
    if set((data.get("dual_family") or {}).get("lenses") or []) - set(LENS_ORDER):
        raise Park("dual_family names an unknown lens")
    bounds = data.get("bounds") or {}
    for key in ("max_verifier_sessions", "max_proven_suggestions", "attempts_per_task"):
        value = bounds.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise Park(f"bounds.{key} must be a positive integer")
    for key in ("max_spend_usd", "max_wall_s"):
        value = bounds.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise Park(f"bounds.{key} must be a positive number")
    return data


def _bounds(label: str, spec: dict[str, Any]) -> None:
    if not isinstance(spec.get("model"), str) or not spec["model"]:
        raise Park(f"{label} needs an explicit model")
    if not isinstance(spec.get("family"), str) or not spec["family"]:
        raise Park(f"{label} needs an explicit family")
    if not isinstance(spec.get("max_turns"), int) or spec["max_turns"] < 1:
        raise Park(f"{label} needs a positive integer max_turns")
    for key in ("budget_usd", "timeout_s"):
        value = spec.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            raise Park(f"{label} needs a positive {key}")


def lens_spec(plan: dict[str, Any], lens: str, *, family: str | None = None) -> dict[str, Any]:
    """The exact ACP session spec for one lens, after routing."""
    lenses = plan["lenses"]
    if lens not in lenses:
        raise Park(f"unknown lens: {lens!r}")
    spec = dict(lenses[lens])
    chosen = family or spec["family"]
    forbidden = spec.get("forbid_families") or []
    if chosen in forbidden:
        raise Park(f"lens {lens} must never run on {chosen}: {forbidden}")
    if chosen not in plan["families"]:
        raise Park(f"lens {lens} routed to an undeclared family: {chosen}")
    if chosen != spec["family"]:
        # A rerouted lens keeps its bounds and takes the family's verifier-grade model.
        spec["model"] = plan["roles"]["verifier"]["models"].get(chosen) or spec["model"]
    spec["family"] = chosen
    return {**spec, **plan["families"][chosen]}


def role_spec(plan: dict[str, Any], role: str, *, family: str | None = None) -> dict[str, Any]:
    spec = dict(plan["roles"][role])
    if role == "verifier":
        if family is None:
            raise Park("a verifier session needs its family")
        spec["family"] = family
        spec["model"] = spec["models"][family]
        spec.pop("models", None)
    chosen = spec["family"]
    if chosen not in plan["families"]:
        raise Park(f"role {role} routed to an undeclared family: {chosen}")
    return {**spec, **plan["families"][chosen]}

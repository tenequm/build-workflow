"""Load and validate the template plan. A stage never guesses what it was pinned to."""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import yaml
from operator_driver.storage import Park

from .proc import ENV_ALLOWLIST

TEMPLATES = Path(__file__).resolve().parents[2] / "templates"
# `implementation` is this project's own lens; the other four are vendored from polish.
LENS_ORDER = ("cleanliness", "design", "efficiency", "gating", "implementation")
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
        # A family may ask for environment names to be redirected per session (see
        # proc.env_overlay). Only allowlisted names qualify: the allowlist is the
        # credential fence, and a template that could name anything could name a
        # provider key back into a reviewer's environment.
        redirect = family.get("env") or []
        if not isinstance(redirect, list) or set(redirect) - set(ENV_ALLOWLIST):
            raise Park(f"family {name} env must name only allowlisted variables")
        # The credential a lane cannot run without. Readiness reports its absence before
        # a session is spawned, because a family that redirects the root its harness
        # keeps credentials under reaches its provider through this name alone, and
        # discovering that mid-run means the lenses before it were paid for.
        needed = family.get("requires_env") or []
        if not isinstance(needed, list) or set(needed) - set(ENV_ALLOWLIST):
            raise Park(f"family {name} requires_env must name only allowlisted variables")
        # Paths removed from the reviewed worktree before the session reads them. They
        # are worktree-relative by construction: the point is to disarm the pull request
        # tree, never to reach outside it.
        strip = family.get("strip_paths") or []
        if not isinstance(strip, list) or not all(
            isinstance(value, str)
            and value
            and not Path(value).is_absolute()
            and ".." not in Path(value).parts
            for value in strip
        ):
            raise Park(f"family {name} strip_paths must be relative paths inside the worktree")
    lenses = data.get("lenses")
    if not isinstance(lenses, dict) or set(lenses) != set(LENS_ORDER):
        raise Park(f"stage template must declare exactly the lenses {LENS_ORDER}")
    for name, lens in lenses.items():
        _bounds(f"lens {name}", lens)
        if not isinstance(lens.get("enabled", True), bool):
            raise Park(f"lens {name} enabled must be a boolean")
        if lens["family"] not in families:
            raise Park(f"lens {name} routes to an undeclared family: {lens['family']}")
        forbidden = lens.get("forbid_families") or []
        if lens["family"] in forbidden:
            raise Park(f"lens {name} is pinned to a family its own brief forbids")
    if not any(lens.get("enabled", True) for lens in lenses.values()):
        raise Park("stage template disables every lens; a review needs at least one")
    roles = data.get("roles") or {}
    for name in ("verifier", "claims"):
        if name not in roles:
            raise Park(f"stage template declares no {name} role")
    _bounds("role claims", roles["claims"])
    verifier = roles["verifier"]
    for key in ("budget_usd", "max_turns", "timeout_s"):
        if key not in verifier:
            raise Park(f"role verifier needs {key}")
    if not isinstance(verifier.get("models"), dict) or set(verifier["models"]) - set(families):
        raise Park("role verifier needs a model per declared family")
    routing = data.get("routing") or {}
    if set(routing.get("opposite") or {}) - set(families):
        raise Park("routing names an undeclared family")
    # The values, not only the keys: an opposite that names a family with no verifier
    # model used to pass here and fail at role_spec, one launched stage later.
    for producer, chosen in (routing.get("opposite") or {}).items():
        if chosen == producer:
            raise Park(f"routing verifies {producer} findings with {producer} itself")
        if chosen not in families:
            raise Park(f"routing verifies {producer} findings with an undeclared family: {chosen}")
        if chosen not in verifier["models"]:
            raise Park(f"routing verifies {producer} findings with {chosen}, which has no model")
    if set(routing.get("reroute_lenses") or []) - set(LENS_ORDER):
        raise Park("routing reroutes an unknown lens")
    # routing.override is set by --family, never authored: it is what the routing
    # evidence cites as the reason a lens ran where it ran, and a template that could
    # write it could make that evidence say something the run did not do.
    if "override" in routing:
        raise Park("routing.override is set by --family, not declared by a template")
    if set((data.get("dual_family") or {}).get("lenses") or []) - set(LENS_ORDER):
        raise Park("dual_family names an unknown lens")
    bounds = data.get("bounds") or {}
    for key in ("max_verifier_sessions", "max_proven_suggestions", "attempts_per_task"):
        value = bounds.get(key)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise Park(f"bounds.{key} must be a positive integer")
    value = bounds.get("max_wall_s")
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise Park("bounds.max_wall_s must be a positive number")
    return data


def active_lenses(plan: dict[str, Any]) -> tuple[str, ...]:
    """The lenses this run actually spawns, in the canonical order.

    A lens is parked with `enabled: false` rather than deleted, so re-admitting one
    when the precision ledger shows it earns its place is a one-line change.
    """
    return tuple(
        lens for lens in LENS_ORDER if plan["lenses"][lens].get("enabled", True) is not False
    )


def model_for(plan: dict[str, Any], label: str, spec: dict[str, Any], family: str) -> str:
    """The model a lens or role runs when it is routed onto `family`.

    Its own `models` map first, because a lens moved onto a verifier-grade model is a
    quieter lens, which is the opposite of why it was moved. The verifier's map is the
    declared fallback. There is no third fallback: keeping the previous family's model
    would launch, say, gpt-5.6-sol on the gemini adapter, and a family swap must never
    silently ask a lane for a model it has never heard of.
    """
    model = (spec.get("models") or {}).get(family) or plan["roles"]["verifier"]["models"].get(
        family
    )
    if not model:
        raise Park(
            f"{label} has no model for family {family}: declare one in its own "
            "`models` map or in roles.verifier.models"
        )
    return str(model)


def override_family(plan: dict[str, Any], family: str) -> dict[str, Any]:
    """Route every producing session of one run onto a single declared family.

    Swapping lanes used to mean authoring another near-copy of stages.yaml -
    stages-fast.yaml and stages-opencode.yaml are two of them, and each differs from
    production in its routing alone. With this, a lane costs a `families:` entry plus a
    verifier model, and the whole run swaps from the command line.

    Verification is deliberately NOT swapped: a finding is verified by a family other
    than the one that produced it, and verify.opposite() still chooses that family. The
    author-opposite reroute and the dual-family second opinion are switched off, because
    both exist to introduce a second family and this asked for one.
    """
    if family not in plan["families"]:
        raise Park(
            f"--family {family} is not declared by this template "
            f"(declared: {', '.join(sorted(plan['families']))})"
        )
    plan = copy.deepcopy(plan)
    for lens in active_lenses(plan):
        spec = plan["lenses"][lens]
        forbidden = spec.get("forbid_families") or []
        if family in forbidden:
            raise Park(f"lens {lens} must never run on {family}: {forbidden}")
        if spec["family"] != family:
            spec["model"] = model_for(plan, f"lens {lens}", spec, family)
            spec["family"] = family
    claims = plan["roles"]["claims"]
    if claims["family"] != family:
        claims["model"] = model_for(plan, "role claims", claims, family)
        claims["family"] = family
    routing = plan.setdefault("routing", {})
    routing["reroute_lenses"] = []
    routing["override"] = family
    plan["dual_family"] = {"lenses": [], "enabled": False}
    return plan


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
        spec["model"] = model_for(plan, f"lens {lens}", spec, chosen)
    spec["family"] = chosen
    spec.pop("models", None)
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

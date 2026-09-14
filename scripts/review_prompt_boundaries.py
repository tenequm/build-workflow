"""Fail when /review-pr host configuration leaks into its production review graph."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVIEW = ROOT / "skills/review-pr/templates"
ROLES = REVIEW / "bernstein-templates/roles"
GOAL = REVIEW / "review-goal.md"
SEED = REVIEW / "review-seed.yaml"
MANAGER = ROLES / "manager/system_prompt.md"
LENSES = sorted(ROLES.glob("lens-*/system_prompt.md"))
MODEL_FACING = [GOAL, MANAGER, ROLES / "report-writer/system_prompt.md", *LENSES]
SKILL = ROOT / "skills/review-pr/SKILL.md"
HARNESS = ROOT / "fixtures/review-pr-cases/harness.py"
EXPECTED_ROLES = {
    "manager",
    "lens-1-claim",
    "lens-2-side-effects",
    "lens-3-design",
    "lens-4-efficiency",
    "lens-5-cleanliness",
    "report-writer",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def seed_roles(source: str) -> set[str]:
    """Read the direct keys under role_model_policy without a YAML dependency."""
    lines = iter(source.splitlines())
    for line in lines:
        if line == "role_model_policy:":
            break
    else:
        return set()
    roles: set[str] = set()
    for line in lines:
        if not line:
            break
        if line.startswith("  ") and not line.startswith("    "):
            roles.add(line.strip().split(":", 1)[0])
    return roles


def main() -> None:
    role_dirs = {path.name for path in ROLES.iterdir() if path.is_dir()}
    require(role_dirs == EXPECTED_ROLES, f"unexpected production roles: {sorted(role_dirs)}")
    require(len(LENSES) == 5, f"expected five lens prompts, found {len(LENSES)}")
    lens_text = [path.read_text() for path in LENSES]
    require(len(set(lens_text)) == 1, "lens executor prompts diverged")

    routing_markers = (
        "review-seed",
        "role_model_policy",
        "litellm/",
        "qwen",
        "gpt-",
        "claude-sonnet",
        "gateway",
    )
    for path in MODEL_FACING:
        lowered = path.read_text().lower()
        for marker in routing_markers:
            require(marker.lower() not in lowered, f"host routing leaked into {path}: {marker}")
        require("shadow" not in lowered, f"measurement leaked into {path}")

    goal = GOAL.read_text().lower()
    for marker in ("task server", "report-writer", "role_model", ".sdd/", "task graph"):
        require(marker not in goal, f"orchestration leaked into review-goal.md: {marker}")

    manager = MANAGER.read_text()
    require("127.0.0.1" not in manager and "8052" not in manager, "manager hardcodes server")

    seed = SEED.read_text().lower()
    routed_roles = seed_roles(SEED.read_text())
    require(
        routed_roles == EXPECTED_ROLES,
        f"seed routes unexpected production roles: {sorted(routed_roles)}",
    )
    goal_text = GOAL.read_text().lower()
    for name, text in (("seed", seed), ("goal", goal_text)):
        require(
            "never commit and never push." in text, f"never-commit constraint missing from {name}"
        )
        require("base branch" in text, f"base-validation constraint missing from {name}")
        require(
            "never from the pull request's own tree" in text,
            f"PR-tree validation ban missing from {name}",
        )

    isolation_flags = (
        "--ignore-user-config",
        "--ignore-rules",
        "--ephemeral",
        "--disable hooks",
        "--disable apps",
        "--disable plugins",
        "--disable plugin_sharing",
        "--disable remote_plugin",
        "project_doc_max_bytes=0",
    )
    for path in (SKILL, HARNESS):
        source = path.read_text()
        for flag in isolation_flags:
            require(flag in source, f"Codex worker isolation missing from {path}: {flag}")

    for flag in ("-ns", "-np", "--no-themes", "--no-session"):
        require(flag in SKILL.read_text(), f"Pi worker isolation missing from skill: {flag}")
        require(flag in HARNESS.read_text(), f"Pi worker isolation missing from harness: {flag}")
    for flag in ("--safe-mode", "--no-session-persistence"):
        require(flag in SKILL.read_text(), f"Claude isolation missing from skill: {flag}")
        require(flag in HARNESS.read_text(), f"Claude isolation missing from harness: {flag}")

    require(
        'ln -s "$work/review-templates"' in SKILL.read_text(),
        "skill copies prompts into RAG scope",
    )
    require(
        "templates.symlink_to(template_snapshot" in HARNESS.read_text(),
        "harness copies prompts into RAG scope",
    )
    for ignored in ("/.bernstein/", "/.sdd/", "/review-report.md"):
        require(ignored in SKILL.read_text(), f"runtime artifact is stageable in skill: {ignored}")
        require(
            ignored in HARNESS.read_text(), f"runtime artifact is stageable in harness: {ignored}"
        )
    print("review prompt boundaries: clean")


if __name__ == "__main__":
    main()

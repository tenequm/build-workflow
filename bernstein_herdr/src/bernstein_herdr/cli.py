"""`bernstein-herdr` CLI.

  bernstein-herdr ready [--plan <yaml>] [--no-validate]   readiness checks + pins -> <run>/readiness/
  bernstein-herdr scorer --step "<title>"                  scorer gate in the current worktree; exit 0/1
  bernstein-herdr judge-verdict --step "<phase title>"     completion signal for a judge step; exit 0 unless the review blocks
  bernstein-herdr agy-session <db> [name] [--steps]        timing and tokens from an Antigravity conversation DB
"""

from __future__ import annotations

import sys
from pathlib import Path


def _arg(argv: list[str], flag: str, default: str | None = None) -> str | None:
    return argv[argv.index(flag) + 1] if flag in argv else default


def main() -> int:
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        return 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "ready":
        from bernstein_herdr.ready import main as ready_main
        return ready_main(rest)
    if cmd == "agy-session":
        from bernstein_herdr.agy_session import main as agy_main
        return agy_main(rest)
    if cmd == "scorer":
        from bernstein_herdr.gates.scorer import score
        blocked, f = score(Path.cwd(), _arg(rest, "--step") or "")
        print(f)
        return 1 if blocked else 0
    if cmd == "judge-verdict":
        from bernstein_herdr.judge import parse_verdict
        from bernstein_herdr.plan import load_plan, repo_root
        from bernstein_herdr import ledger
        plan = load_plan(root=repo_root(Path.cwd()))
        step = plan.step(_arg(rest, "--step") or "")
        review = Path.cwd() / ".agents" / "blind-review.md"
        v = parse_verdict(review)
        dest = plan.run_dir / "judge" / step.slug
        dest.mkdir(parents=True, exist_ok=True)
        if review.exists():
            (dest / "blind-review.md").write_text(review.read_text())
        sc = Path.cwd() / ".agents" / "scorecard.md"
        if sc.exists():
            (dest / "scorecard.md").write_text(sc.read_text())
        ledger.row(plan.run_dir, {"run_id": f"{plan.slug}-{step.slug}-judge", "step": step.slug, "gate": "judge_step", "evidence": "verified", **v})
        print(v)
        return 1 if v["block"] else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())

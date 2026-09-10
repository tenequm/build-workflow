#!/usr/bin/env python3
"""Apply the cutover prerequisites to an operator-owned Bernstein source checkout.

Fails on unfamiliar source; never downloads, commits, or installs anything. Rebuild
the source installation afterward. The driver independently checks the installed code.
"""

from __future__ import annotations

import argparse
from pathlib import Path

PATCHES = (
    (
        "src/bernstein/core/git/git_basic.py",
        '    # Guardrail: never push to "master" - auto-correct to "main".',
        "    # Operator phase builds end local: do not fetch, rebase or push.\n"
        "    import os\n"
        '    if os.environ.get("BERNSTEIN_OPERATOR_LOCAL_ONLY") == "1":\n'
        '        return GitResult(returncode=0, stdout="", stderr="operator local-only: push skipped")\n\n'
        '    # Guardrail: never push to "master" - auto-correct to "main".',
    ),
    (
        "src/bernstein/core/orchestration/orchestrator.py",
        "        self._response_cache = ResponseCacheManager(workdir)",
        "        self._response_cache = (\n"
        '            None if os.environ.get("BERNSTEIN_RESPONSE_CACHE", "1") == "0"\n'
        "            else ResponseCacheManager(workdir)\n"
        "        )",
    ),
    (
        "src/bernstein/core/orchestration/orchestrator.py",
        '            _had_any_terminal_task = bool(refreshed_tasks_by_status["done"] '
        'or refreshed_tasks_by_status["failed"])',
        "            # Operator: a merged task is soft-archived to CLOSED, a status the\n"
        "            # default fetch omits, so a fully merged run never self-stops and\n"
        "            # never journals the run_quiescence its phase boundary requires.\n"
        "            _had_any_terminal_task = bool(\n"
        '                refreshed_tasks_by_status["done"]\n'
        '                or refreshed_tasks_by_status["failed"]\n'
        '                or fetch_all_tasks(self._client, base, ["closed"])["closed"]\n'
        "            )",
    ),
    (
        "src/bernstein/core/config/seed_parser.py",
        "    if name not in VALID_GATE_NAMES:\n"
        '        raise SeedError(f"quality_gates.pipeline[{index}].name is unsupported: {name!r}")',
        "    if name not in VALID_GATE_NAMES:\n"
        "        from pathlib import Path\n"
        "        from bernstein.core.quality.gate_plugins import GatePluginRegistry\n"
        "\n"
        "        if GatePluginRegistry(Path.cwd(), built_in_names=VALID_GATE_NAMES).get(name) is None:\n"
        '            raise SeedError(f"quality_gates.pipeline[{index}].name is unsupported: {name!r}")',
    ),
)


def prepare(root: Path, *, check: bool = False) -> list[str]:
    # Two patches share orchestrator.py, so each edit must build on the previous
    # one's text; deriving both from the original file would drop the first write.
    pending: dict[Path, str] = {}
    for rel, before, after in PATCHES:
        path = root / rel
        source = pending.get(path, path.read_text())
        if after in source:
            continue
        if source.count(before) != 1:
            raise RuntimeError(
                f"unfamiliar engine source at {rel}; inspect the upstream implementation"
            )
        pending[path] = source.replace(before, after)
    if check and pending:
        raise RuntimeError("source checkout still needs the operator prerequisite patches")
    for path, replacement in pending.items():
        path.write_text(replacement)
    return [str(path.relative_to(root)) for path in pending]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for changed in prepare(args.source.resolve(), check=args.check):
        print(changed)

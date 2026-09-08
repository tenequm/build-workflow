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
    edits = []
    for rel, before, after in PATCHES:
        path = root / rel
        source = path.read_text()
        if after in source:
            continue
        if source.count(before) != 1:
            raise RuntimeError(
                f"unfamiliar engine source at {rel}; inspect the upstream implementation"
            )
        edits.append((path, source.replace(before, after)))
    if check and edits:
        raise RuntimeError("source checkout still needs the operator prerequisite patches")
    for path, replacement in edits:
        path.write_text(replacement)
    return [str(path.relative_to(root)) for path, _ in edits]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for changed in prepare(args.source.resolve(), check=args.check):
        print(changed)

"""`herdr-fake`: an executor kind that exercises the plumbing without a model.

Everything a real executor step touches still happens -- pins are checked, the brief
is written into the worktree, a tab opens in the run's herdr workspace, a watcher
settles the pane, the scorer runs and `bernstein task complete` is posted -- but the
thing in the pane is a shell script, so a run costs seconds and no tokens. Use it to
test the chain itself (dependencies, parallelism, gates, merge, judge) and never to
test whether work got done.

herdr has no `agent start --kind` value for a plain script, so the script is started
with `herdr pane run` and reports its own lifecycle to herdr with `pane report-agent`
(working on entry, idle before it returns to the prompt). A pane carrying a reported
agent answers `herdr agent get <pane id>`, which is exactly what the watcher polls --
so the watcher's target for this kind is the pane id rather than an agent name, and
nothing else in the settle path changes.

The script reads its inputs from the FAKE_* environment the adapter sets, appends one
line to the file named by the sidecar's `fake_touch` (default `FAKE.md`, which must be
in the step's `files` allowlist or the scorer blocks), runs the sidecar's real
`gate_cmd` and writes its real exit code into the report, and commits nothing.
"""

from __future__ import annotations

import shlex
import time
from pathlib import Path

from bernstein_herdr import adapter, herdr

DEFAULT_TOUCH = "FAKE.md"
SCRIPT_NAME = "fake-executor.sh"
REPORT_SOURCE = "bernstein-herdr-fake"

SCRIPT = r"""#!/bin/sh
# Written by bernstein_herdr.fake; edits here are overwritten on the next spawn.
set -u
cd "$FAKE_WORKTREE" || exit 1
report_state() { "${HERDR_BIN:-herdr}" pane report-agent "$FAKE_PANE" --source bernstein-herdr-fake --agent "$FAKE_AGENT" --state "$1" >/dev/null 2>&1; }
report_state working
[ -f "$FAKE_BRIEF" ] || echo "herdr-fake: no brief at $FAKE_BRIEF"
printf 'herdr-fake %s step=%s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$FAKE_STEP" >> "$FAKE_TOUCH"
sh -c "$FAKE_GATE" >/dev/null 2>&1
rc=$?
mkdir -p "$(dirname "$FAKE_REPORT")"
cat > "$FAKE_REPORT" <<EOF
# Report: $FAKE_STEP (herdr-fake)

Plumbing-test executor. No model ran; no source file was authored.

## Items

1. Appended one line to $FAKE_TOUCH -- done.
2. Ran the step gate and recorded its exit code -- done.

## Validation

\`\`\`
$FAKE_GATE
\`\`\`

exit code: $rc

## Deviations

none
EOF
report_state idle
echo "herdr-fake done: report=$FAKE_REPORT gate_rc=$rc"
"""


def write_script(run_dir: Path) -> Path:
    """The script lives in the run directory, never in the worktree: an untracked file
    inside the worktree would show up in the scorer's changed-file set."""
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / SCRIPT_NAME
    path.write_text(SCRIPT)
    path.chmod(0o755)
    return path


def _sidecar(plan, step, key: str, default: str) -> str:
    steps = plan.sidecar.get("steps", {}).get(step.title, {})
    return str(steps.get(key, plan.sidecar.get("defaults", {}).get(key, default)))


class HerdrFakeAdapter(adapter.HerdrAdapter):
    """Plumbing-test executor: no model, no effort, a shell script in the pane."""

    kind = "fake"
    agent_args: list[str] = []
    model = ""
    effort = ""

    def launch(self, *, name: str, pane: str, args: list[str], plan, step, root: Path, workdir: Path, brief_rel: str) -> tuple[float, str]:
        env = {
            "FAKE_WORKTREE": str(workdir),
            "FAKE_BRIEF": brief_rel,
            "FAKE_REPORT": step.report_rel,
            "FAKE_STEP": step.slug,
            "FAKE_TOUCH": _sidecar(plan, step, "fake_touch", DEFAULT_TOUCH),
            "FAKE_GATE": _sidecar(plan, step, "gate_cmd", "just check"),
            "FAKE_AGENT": name,
            "FAKE_PANE": pane,
        }
        script = write_script(plan.run_dir)
        # Register the pane agent before the script starts: the watcher polls
        # immediately, and an unregistered pane reads as `gone`, which it treats as an
        # agent that died before writing a report.
        herdr.call("pane", "report-agent", pane, "--source", REPORT_SOURCE, "--agent", name, "--state", "working")
        # `herdr pane run` joins its argv with spaces and types the result at the shell
        # prompt, so quoting has to survive inside each token -- an unquoted
        # `FAKE_GATE=sh ./check.sh` silently becomes two words and nothing runs.
        cmd = ["env", *(shlex.quote(f"{k}={v}") for k, v in env.items()), "sh", shlex.quote(str(script))]
        herdr.call("pane", "run", pane, *cmd)
        # The watcher polls `herdr agent get <target>`; a pane with a reported agent
        # answers to its pane id, and there is no agent record under `name`.
        return time.time(), pane


adapter.ADAPTER_BY_KIND.setdefault("fake", HerdrFakeAdapter)

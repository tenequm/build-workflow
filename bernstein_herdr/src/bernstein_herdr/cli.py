"""`bernstein-herdr` CLI.

  bernstein-herdr ready [--plan <yaml>] [--no-validate]   readiness checks + pins -> <run>/readiness/
  bernstein-herdr run-config [--plan <yaml>]                run_config.json, run port, base_ref check
  bernstein-herdr scorer --step "<title>"                  scorer gate in the current worktree; exit 0/1
  bernstein-herdr judge-verdict --step "<phase title>"     completion signal for a judge step; exit 0 unless the review blocks
  bernstein-herdr agy-session <db> [name] [--steps]        timing and tokens from an Antigravity conversation DB
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml


def _arg(argv: list[str], flag: str, default: str | None = None) -> str | None:
    return argv[argv.index(flag) + 1] if flag in argv else default


#: What Bernstein reads out of run_config.json (orchestrator.py:7126-7134). `pr` is the
#: default merge_strategy, and on `pr` the approval gate pushes to origin and skips the
#: merge-back entirely (orchestrator.py:826-832), so a run that must land on the
#: integration branch has to say `direct` here. No seed key reaches this file.
RUN_CONFIG = {"approval": "auto", "merge_strategy": "direct", "auto_merge": True, "dry_run": False}


def free_port(preferred: int) -> int:
    """`preferred` when nothing holds it, else a port the OS says is free.

    `bernstein run --port` defaults to 8052 for every run in every repo, so two runs (or
    one run and the orchestrator a killed run left behind) collide on it: the newcomer
    talks to the old server, which 401s it. A port per run removes the collision; the
    refusal below still covers a live run of THIS repo.
    """
    import socket

    with socket.socket() as s:
        s.settimeout(0.5)
        if s.connect_ex(("127.0.0.1", preferred)) != 0:
            return preferred
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def stale_bernstein_pids(root: Path) -> list[tuple[int, str]]:
    """Live `bernstein` processes belonging to this repo, by argv or by cwd.

    A killed run does not take its orchestrator and watchdog with it. They keep ticking
    against `.sdd/` under the same root and respawn tasks into the NEXT run's
    directories -- the 2026-09-02 replay lost a whole run to two orphans from the
    previous one. The port refusal above only sees the task server, which is a different
    process and may already be gone, so match on the repo instead: the root in the argv,
    or the root (or a path under it) as the process cwd.
    """
    import os
    import subprocess

    listing = subprocess.run(["pgrep", "-fl", "bernstein"], capture_output=True, text=True, check=False).stdout
    hits: list[tuple[int, str]] = []
    for line in listing.splitlines():
        pid_s, _, cmd = line.partition(" ")
        if not pid_s.isdigit() or int(pid_s) == os.getpid():
            continue
        pid = int(pid_s)
        if str(root) in cmd:
            hits.append((pid, cmd[:120]))
            continue
        cwd = subprocess.run(["lsof", "-p", str(pid), "-a", "-d", "cwd", "-Fn"], capture_output=True, text=True, check=False).stdout
        for l in cwd.splitlines():
            if l.startswith("n") and (l[1:] == str(root) or l[1:].startswith(f"{root}/")):
                hits.append((pid, cmd[:120]))
                break
    return hits


def run_config(root: Path, plan_path: Path | None = None) -> int:
    """Write `.sdd/runtime/run_config.json`, pick this run's port, check base_ref.

    Three things that must be true before `bernstein run` and that nothing else checks:

    - the run needs a port of its own; the chosen one is printed as the `--port` to pass
      and written to `.sdd/runtime/server.port`, which is where `resolve_server_url()`
      (cli/helpers.py:152) and therefore the watcher's own status and fail probes read
      it, so nothing else has to be told about it;
    - a task server answering on this repo's recorded port is a live run of the same
      plan, so this refuses rather than joining it;
    - and any other `bernstein` process whose argv or cwd names this root is an
      orchestrator or watchdog a killed run left behind; it is listed with the kill
      command, never killed automatically;
    - `quality_gates.base_ref` in bernstein.yaml must be the integration branch checked
      out at the root. Left at the default `main` the gates diff the whole branch, and
      `run_config` blocked a merge over a file the agent never touched. It is only
      reported here, never rewritten: bernstein.yaml is tracked and an uncommitted edit
      lands in the agent's changed-file set, which is the same block by another door.
    """
    import json
    import socket
    import subprocess

    branch = subprocess.run(["git", "symbolic-ref", "--short", "-q", "HEAD"], cwd=root,
                            capture_output=True, text=True, check=False).stdout.strip()
    if not branch or branch in ("main", "master"):
        print(f"refusing: repo root is on {branch or 'a detached HEAD'}; check out the integration branch")
        return 1
    port_file = root / ".sdd" / "runtime" / "server.port"
    recorded = int(port_file.read_text().strip()) if port_file.exists() else 0
    if recorded:
        with socket.socket() as s:
            s.settimeout(0.5)
            if s.connect_ex(("127.0.0.1", recorded)) == 0:
                print(f"refusing: a task server for this repo is alive on port {recorded}; stop that run first "
                      f"(`bernstein quarantine list` and `bernstein quarantine clear --task <title>` if it left a task quarantined)")
                return 1
    stale = stale_bernstein_pids(root)
    if stale:
        listing = "\n".join(f"  {pid}  {cmd}" for pid, cmd in stale)
        print(f"refusing: {len(stale)} bernstein process(es) already belong to this repo (orchestrator, watchdog or "
              f"task server left by an earlier run). They tick against .sdd/ and respawn tasks into this run's "
              f"directories.\n{listing}\nkill them yourself, then rerun:\n  kill {' '.join(str(p) for p, _ in stale)}")
        return 1
    port = free_port(recorded or 8052)
    seed = (root / "bernstein.yaml").read_text() if (root / "bernstein.yaml").exists() else ""
    declared = yaml.safe_load(seed).get("quality_gates", {}).get("base_ref") if seed else None
    if declared != branch:
        print(f"refusing: bernstein.yaml quality_gates.base_ref is {declared!r}, not the checked-out {branch!r}; fix and commit it")
        return 1
    out = root / ".sdd" / "runtime" / "run_config.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(RUN_CONFIG))
    port_file.write_text(f"{port}\n")
    from bernstein_herdr.plan import load_plan

    run_dir = load_plan(plan_path, root=root).run_dir
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "bernstein.json").write_text(json.dumps({"port": port, "base_ref": branch}))
    print(f"{out}: {json.dumps(RUN_CONFIG)}\nbase_ref={branch}\nrun with: --port {port}")
    return 0


def main() -> int:
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        return 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "run-config":
        from bernstein_herdr.plan import repo_root
        plan = _arg(rest, "--plan")
        return run_config(repo_root(Path.cwd()), Path(plan) if plan else None)
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
        from bernstein_herdr.judge import record_verdict
        from bernstein_herdr.plan import load_plan, repo_root
        plan = load_plan(root=repo_root(Path.cwd()))
        v = record_verdict(plan, plan.step(_arg(rest, "--step") or ""), Path.cwd())
        print(v)
        return 1 if v["block"] else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())

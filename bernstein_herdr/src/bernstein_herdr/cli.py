"""`bernstein-herdr` CLI.

  bernstein-herdr ready [--plan <yaml>] [--no-validate]   readiness checks + pins -> <run>/readiness/
  bernstein-herdr run-config [--plan <yaml>]                run_config.json, run port, base_ref + base_sha
  bernstein-herdr gate                                     THE quality gate: run by Bernstein from the agent worktree
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

    seed = (root / "bernstein.yaml").read_text() if (root / "bernstein.yaml").exists() else ""
    declared = yaml.safe_load(seed).get("quality_gates", {}).get("base_ref") if seed else None
    branch = subprocess.run(["git", "symbolic-ref", "--short", "-q", "HEAD"], cwd=root,
                            capture_output=True, text=True, check=False).stdout.strip()
    if not branch or branch in ("main", "master"):
        print(f"refusing: repo root is on {branch or 'a detached HEAD'}; check out the integration branch")
        return 1
    # A warm-pool spawn runs an agent AT THE ROOT and leaves the root checkout on that
    # agent's branch (measured 2026-09-02). Nothing puts it back, and the next run's
    # merges would land on the leftover branch instead of the integration branch, so the
    # work silently never reaches it. Refuse before the run, with the recovery command.
    if branch.split("/", 1)[0] in ("agent", "salvage", "spec"):
        target = declared or "<integration branch>"
        print(f"refusing: the repo root is checked out on {branch!r}, a branch a warm-pool spawn left behind; "
              f"every merge of the next run would land there instead of the integration branch. Recover with:\n"
              f"  git -C {root} checkout {target}\n"
              f"then rerun. (Check `git -C {root} log {target}..{branch}` first if that branch may hold work.)")
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
    if declared != branch:
        print(f"refusing: bernstein.yaml quality_gates.base_ref is {declared!r}, not the checked-out {branch!r}; fix and commit it")
        return 1
    out = root / ".sdd" / "runtime" / "run_config.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(RUN_CONFIG))
    port_file.write_text(f"{port}\n")
    from bernstein_herdr.plan import load_plan

    plan = load_plan(plan_path, root=root)
    run_dir = plan.run_dir
    run_dir.mkdir(parents=True, exist_ok=True)
    # The integration branch at run start. Every merge advances that branch, so a judge
    # that diffs `<integration branch>..HEAD` after its dependency merged sees NOTHING
    # (measured 2026-09-02: "The diff is empty: build/smoke and HEAD both resolve to
    # da72e9e", a correct do-not-merge for the wrong reason). The frozen sha is the only
    # ref that still names where this run began. It is also written as a git ref so a
    # judge inside a worktree can name it without reaching outside its tree for a file.
    base_sha = subprocess.run(["git", "rev-parse", branch], cwd=root, capture_output=True, text=True, check=False).stdout.strip()
    ref = f"refs/build/base/{plan.slug}"
    subprocess.run(["git", "update-ref", ref, base_sha], cwd=root, capture_output=True, check=False)
    (run_dir / "bernstein.json").write_text(json.dumps({"port": port, "base_ref": branch, "base_sha": base_sha, "base_ref_name": ref}))
    print(f"{out}: {json.dumps(RUN_CONFIG)}\nbase_ref={branch}\nbase_sha={base_sha} ({ref})\nrun with: --port {port}")
    return 0


def task_for_worktree(root: Path, agent_id: str) -> dict:
    """The Bernstein task record this worktree belongs to, from `.sdd/runtime` state.

    The per-task CLAUDE.md that carries the title is deleted before the gates run
    (`quality_gates.py:1105` calls `restore_claude_md` on purpose), so the surviving
    channel is the worktree directory NAME: it is the agent_id, `team.json` maps that to
    task ids and `tasks.jsonl` maps those to a title. tasks.jsonl is append-only with one
    record per version, so the last record for an id is its current state. Batching can
    hand one agent two tasks; the last one claimed is the one being gated, and the row
    records every id so a mis-pick is visible.
    """
    import json

    rt = root / ".sdd" / "runtime"
    team = json.loads((rt / "team.json").read_text())
    member = next((m for m in team.get("members", []) if m.get("agent_id") == agent_id), None)
    if member is None:
        raise RuntimeError(f"no team.json member for agent {agent_id!r} (worktree {agent_id})")
    ids = list(member.get("task_ids") or [])
    latest: dict[str, dict] = {}
    for line in (rt / "tasks.jsonl").read_text().splitlines():
        if line.strip():
            rec = json.loads(line)
            latest[rec["id"]] = rec
    records = [latest[i] for i in ids if i in latest]
    if not records:
        raise RuntimeError(f"no tasks.jsonl record for task_ids {ids} of agent {agent_id!r}")
    records.sort(key=lambda r: r.get("claimed_at") or 0)
    return records[-1]


def wall_seconds(task: dict, wt: Path, base: str) -> tuple[int, str]:
    """Seconds since the executor started, and which clock said so."""
    import subprocess
    import time

    claimed = task.get("claimed_at") or 0
    if claimed:
        return int(time.time() - claimed), "tasks.jsonl claimed_at"
    log = subprocess.run(["git", "log", "--format=%ct", f"{base}..HEAD"], cwd=wt,
                         capture_output=True, text=True, check=False).stdout.split()
    if log:
        return int(time.time() - int(log[-1])), "first commit in the worktree"
    return 0, "unknown (no claimed_at, no commit)"


def gate(argv: list[str]) -> int:
    """The quality gate, run by Bernstein in the agent worktree before the merge.

    Wired as `quality_gates.pipeline: [{name: tests, required: true, condition: always,
    command_override: bernstein-herdr gate}]`. `command_override` is what makes it run
    verbatim: without it the built-in tests gate composes its own command and returns None
    (skipping the gate entirely) when no Python file changed, whatever `condition` says
    (`gate_runner.py:1613-1634`).

    Exit 1 blocks the merge and is TERMINAL: no retry, no escalation, no quarantine -- the
    branch goes to `salvage/<agent>` and a row lands in `.sdd/runtime/refused_merges.jsonl`
    (measured). So the failing path archives and writes its ledger row too; nothing runs
    after it.
    """
    import json
    import shutil
    import subprocess

    from bernstein_herdr import judge, ledger
    from bernstein_herdr.gates.scorer import score
    from bernstein_herdr.plan import load_plan, repo_root

    wt = Path.cwd()
    try:
        root = repo_root(wt)
        if wt == root:
            # A warm-pool spawn gets no worktree: Bernstein claims a pre-created slot,
            # writes the task-specific CLAUDE.md to the ROOT and runs the agent there on
            # an `agent/<session>` branch, so the root checkout leaves the integration
            # branch and every later merge lands on that agent branch instead (measured
            # 2026-09-02: `Warm pool: claimed slot spec-<task>` then `Wrote task-specific
            # CLAUDE.md to CLAUDE.md`). Blocking here fails that task; the retry gets a
            # real worktree. The root branch must be put back by hand.
            branch = subprocess.run(["git", "symbolic-ref", "--short", "-q", "HEAD"], cwd=wt,
                                                  capture_output=True, text=True, check=False).stdout.strip()
            print(f"gate: BLOCKING -- this step is running at the REPO ROOT {root}, not in a worktree "
                  f"(warm-pool spawn). The root is now on branch {branch!r}; put it back on the integration "
                  f"branch with `git checkout <integration branch>` or later merges land on the agent branch.")
            return 1
        task = task_for_worktree(root, wt.name)
        plan = load_plan(root=root)
        step = plan.step(task["title"])
    except Exception as exc:
        print(f"gate: cannot identify the step for worktree {wt} -- blocking: {exc}")
        return 1
    # Bernstein invokes the pipeline TWICE per task, about a second apart, so without a
    # memo every row, archive and ledger line is doubled and the wall_s of the second
    # copy is wrong. The memo is keyed on (task id, worktree HEAD): the same task at the
    # same commit is the same verdict, and a genuine re-gate after a repair commit has a
    # different HEAD and is scored afresh.
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=wt, capture_output=True, text=True, check=False).stdout.strip()
    memo = plan.run_dir / "gate-memo" / f"{task['id']}-{head[:12]}.json"
    if memo.exists():
        rec = json.loads(memo.read_text())
        print(f"gate: replaying the recorded result for task {task['id']} at {head[:12]} "
              f"(gate already ran at {rec['ts']}); no new row, no new archive")
        print(json.dumps(rec["row"], separators=(",", ":")))
        return int(rec["rc"])

    def remember(row: dict, rc: int) -> int:
        memo.parent.mkdir(parents=True, exist_ok=True)
        memo.write_text(json.dumps({"ts": ledger.now(), "head": head, "rc": rc, "row": row}, separators=(",", ":")))
        return rc

    wall, wall_src = wall_seconds(task, wt, step.base)
    common = {"run_id": f"{plan.slug}-{step.slug}", "step": step.slug, "task_id": task["id"],
              "agent": wt.name, "wall_s": wall, "wall_src": wall_src, "evidence": "verified"}
    print(f"gate: step={step.slug} title={task['title']!r} task={task['id']} worktree={wt} head={head[:12]} wall_s={wall} ({wall_src})")

    if step.judges:
        verdict = judge.record_verdict(plan, step, wt)
        blocked = bool(verdict["block"]) or bool(verdict.get("certain_mentions"))
        row = {**common, "gate": "judge", "blocked": blocked, **verdict}
        ledger.row(plan.run_dir, row)
        ledger.note(plan.run_dir, f"gate {step.slug} judge blocked={blocked} review_present={verdict['review_present']}")
        print(json.dumps(row, separators=(",", ":")))
        return remember(row, 1 if blocked else 0)

    blocked, f = score(wt, task["title"])
    dest = plan.run_dir / "reports" / step.slug
    stats = ledger.archive(wt, step.base, dest)
    report = wt / step.report_rel
    if report.exists():
        shutil.copy(report, dest / "report.md")
    row = {**common, "gate": "scorer", "blocked": blocked, **stats, "gate_rc": f["gate"]["rc"],
           "allowlist_violations": f["allowlist_violations"], "report_present": report.exists()}
    ledger.row(plan.run_dir, row)
    ledger.note(plan.run_dir, f"gate {step.slug} scorer blocked={blocked} rc={f['gate']['rc']} files={stats['files']}")
    print(json.dumps({k: v for k, v in f.items() if k != "gate"}, separators=(",", ":")))
    print(f"gate_rc={f['gate']['rc']} tail:\n{f['gate']['tail'][-600:]}")
    print(json.dumps(row, separators=(",", ":")))
    return remember(row, 1 if blocked else 0)


def main() -> int:
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        return 2
    cmd, rest = argv[0], argv[1:]
    if cmd == "gate":
        return gate(rest)
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

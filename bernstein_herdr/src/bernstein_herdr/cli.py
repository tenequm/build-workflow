"""`bernstein-herdr` CLI.

  bernstein-herdr ready [--plan <yaml>] [--no-validate]   readiness checks + pins -> <run>/readiness/
  bernstein-herdr run-config [--plan <yaml>] [--resume]     run_config.json, run port, base_ref + base_sha; --resume derives a pruned <slug>-resume plan first
  bernstein-herdr gate                                     THE quality gate: run by Bernstein from the agent worktree
  bernstein-herdr scorer --step "<title>"                  scorer gate in the current worktree; exit 0/1
  bernstein-herdr judge-verdict --step "<phase title>"     completion signal for a judge step; exit 0 unless the verdict is `do not merge`
  bernstein-herdr fix-noop --step "<fix step title>"       write and commit the no-op report when the judge counted 0 certain defects; exit 1 otherwise
  bernstein-herdr watch [--interval N] [--stall M] [--until-stall]   event lines for a live run; exits on run end
"""

from __future__ import annotations

import re
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


from bernstein_herdr.proc import stale_bernstein_pids  # noqa: E402  (re-export; run-config and gate call it)


SHA_TAIL = re.compile(r"-([0-9a-f]{7,40})$")


def completed_steps(rows: list[dict], reports_dir: Path, is_ancestor) -> set[str]:
    """Completion tokens proven by the ledger, for `run-config --resume`.

    A row completes a step when its gate is `scorer` or `judge_step`, its evidence
    is `verified`, and it is not blocked. When the row's `archive` key or the
    reports directory (`<run>/reports/<step>/<task>-<head>/`, `latest` preferred)
    yields a head sha, that sha must additionally satisfy `is_ancestor` -- work
    that is no longer on the branch is not complete. Scorer rows yield their step
    slug; `judge_step` rows carry the JUDGED phase's slug, so they yield
    `judge:<judged slug>` and mark the judge step, never the phase, complete.
    """
    done: set[str] = set()
    for row in rows:
        gate = row.get("gate")
        if gate not in ("scorer", "judge_step") or row.get("evidence") != "verified":
            continue
        if row.get("blocked") or row.get("block"):
            continue
        slug = row.get("step")
        if not slug:
            continue
        m = SHA_TAIL.search(row.get("archive") or "")
        sha = m.group(1) if m else ""
        if not sha and (reports_dir / slug).is_dir():
            latest = reports_dir / slug / "latest"
            names = [latest.resolve().name] if latest.is_symlink() else                     sorted(d.name for d in (reports_dir / slug).iterdir() if d.is_dir())
            for name in names:
                m = SHA_TAIL.search(name)
                if m:
                    sha = m.group(1)
        if sha and not is_ancestor(sha):
            continue
        done.add(f"judge:{slug}" if gate == "judge_step" else slug)
    return done


def _derive_resume(root: Path, plan) -> tuple[object, list[str]] | str:
    """Write `<slug>-resume` plan + sidecar with completed steps pruned; update ACTIVE.

    Returns (resume Plan, pruned titles) or an error string. Classification is
    `completed_steps` over `<run>/runs.jsonl`; ancestry is checked against the
    root's current HEAD, so work stranded off the branch re-runs.
    """
    import json
    import subprocess

    from bernstein_herdr.plan import load_plan

    runs = plan.run_dir / "runs.jsonl"
    if not runs.exists():
        return f"refusing --resume: no {runs}; nothing recorded to resume from"
    rows = [json.loads(l) for l in runs.read_text().splitlines() if l.strip()]

    def is_ancestor(sha: str) -> bool:
        return subprocess.run(["git", "merge-base", "--is-ancestor", sha, "HEAD"],
                              cwd=root, capture_output=True, check=False).returncode == 0

    completed = completed_steps(rows, plan.run_dir / "reports", is_ancestor)
    pruned: list[str] = []
    for raw in plan.steps():
        st = plan.step(raw["title"])
        token = f"judge:{plan.step(st.judges).slug}" if st.judges else st.slug
        if token in completed:
            pruned.append(raw["title"])
    if not pruned:
        return "refusing --resume: no step classifies as complete; run the plan as it stands"
    stages = []
    for stage in plan.data.get("stages", []):
        kept = [s for s in stage.get("steps", []) if s.get("title") not in pruned]
        if kept:
            stages.append({**stage, "steps": kept})
    if not stages:
        return "refusing --resume: every step is complete; there is nothing left to run"
    live = {st.get("name") for st in stages}
    stages = [{**st, **({"depends_on": [d for d in st.get("depends_on") or [] if d in live]}
                        if st.get("depends_on") else {})} for st in stages]
    name = f"{plan.slug}-resume"
    plans_dir = root / ".agents" / "build" / "plans"
    (plans_dir / f"{name}.yaml").write_text(yaml.safe_dump({**plan.data, "name": name, "stages": stages}, sort_keys=False))
    (plans_dir / f"{name}.steps.yaml").write_text(yaml.safe_dump(plan.sidecar, sort_keys=False))
    (plans_dir / "ACTIVE").write_text(f"{name}.yaml")
    return load_plan(plans_dir / f"{name}.yaml", root=root), pruned


def run_config(root: Path, plan_path: Path | None = None, resume: bool = False) -> int:
    """Write `.sdd/runtime/run_config.json`, pick this run's port, check base_ref.

    Three things that must be true before `bernstein run` and that nothing else checks:

    - the run needs a port of its own; the chosen one is printed as the `--port` to pass
      and written to `.sdd/runtime/server.port`, which is where `resolve_server_url()`
      (cli/helpers.py:152) reads it for `bernstein status` at the root. Agents do NOT
      see it: their prompt and the claude hook URL come from `BERNSTEIN_SERVER_URL`
      (spawner_core._resolve_task_server_url, default 8052), so the run must be
      launched with that variable set to the same port, as the printed line shows;
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
    from bernstein_herdr.plan import load_plan

    plan = load_plan(plan_path, root=root)
    if resume:
        derived = _derive_resume(root, plan)
        if isinstance(derived, str):
            print(derived)
            return 1
        plan, pruned = derived
        print(f"resume: pruned {len(pruned)} completed step(s): " + "; ".join(pruned))
        print(f"resume: wrote .agents/build/plans/{plan.slug}.yaml + .steps.yaml, ACTIVE now names it; "
              f"COMMIT both plan files (executor worktrees only see tracked files), rerun readiness, "
              f"then launch with the plan path below")
    out = root / ".sdd" / "runtime" / "run_config.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(RUN_CONFIG))
    port_file.write_text(f"{port}\n")
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
    if resume:
        print(f"next: bernstein run .agents/build/plans/{plan.slug}.yaml --auto-approve --quiet --fresh --port {port}")
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


def merged_ahead(wt: Path, sha: str, base_sha: str, integration: str) -> bool:
    """`sha` carries work of this run AND is already on the integration branch.

    "Ancestor of the integration branch" ALONE is the wrong test, and it cost the
    2026-09-03 acceptance the whole run: the frozen base is trivially an ancestor of the
    branch it was frozen from, so a worktree whose HEAD is still the base -- an executor
    killed before it committed anything -- looked merged. Both dead attempts printed
    `already merged` and exited 0 with no row, no archive and no scorer; `runs.jsonl` was
    never created and 14 files of finished work were discarded unscored.

    A worktree at, or behind, the frozen base has done NOTHING, and doing nothing is a
    normal gate call: it must be SCORED, where an empty diff blocks it honestly. So the
    short-circuit also demands `sha` be strictly AHEAD of `base_sha`. With no `base_sha`
    recorded there is nothing to be ahead of and the short-circuit is off.
    """
    import subprocess

    def ancestor(a: str, b: str) -> bool:
        return subprocess.run(["git", "merge-base", "--is-ancestor", a, b], cwd=wt,
                              capture_output=True, check=False).returncode == 0

    if not (integration and base_sha and sha):
        return False
    return not ancestor(sha, base_sha) and ancestor(sha, integration)


def short_circuit_sha(wt: Path, memo_dir: Path, task_id: str, base_sha: str, integration: str) -> str:
    """The sha the gate may skip re-scoring on, or "" -- ONLY a PASS memo's sha qualifies.

    The rule used to be "any memo for this task proves the gate scored it", and a BLOCKING
    memo is a memo: in the 2026-09-03 acceptance phase-1's attempt 2 blocked and wrote one,
    then attempt 3 -- sitting at the integration branch tip with no commit of its own -- was
    waved through as `already merged`, with no row, no archive, and the task went `done`
    (finding S). A blocked attempt is evidence the step is NOT finished.

    The worktree's own HEAD is not a candidate either. It is only ever interesting when the
    task passed, and then `<task>-merged.json` already names the right sha; a HEAD that
    merely sits on the merged branch having committed nothing satisfies `merged_ahead`
    exactly as well as one that did the work, which is the hole that let S through.
    """
    import json

    passed = memo_dir / f"{task_id}-merged.json"
    if not passed.exists():
        return ""
    sha = json.loads(passed.read_text()).get("head", "")
    return sha if merged_ahead(wt, sha, base_sha, integration) else ""


def fix_noop(cwd: Path, title: str) -> int:
    """The fix step's no-op path as a command, so no model has to transcribe it.

    Reads the judged phase's `<run>/judge/<phase slug>/verdict.json` (the fix
    sidecar's `fixes:` names the phase). ONLY when the verdict is legal, both
    counts are declared, and `certain` is 0: writes the no-op report at the
    step's report path, `git add -f` + commits it, prints DONE, exits 0. Any
    other state prints why and exits 1 without writing anything.
    """
    import json
    import subprocess

    from bernstein_herdr.judge import VERDICTS
    from bernstein_herdr.plan import load_plan, repo_root

    if not title:
        print('fix-noop: pass --step "<fix step title>"')
        return 1
    try:
        plan = load_plan(root=repo_root(cwd))
        step = plan.step(title)
    except Exception as exc:
        print(f"fix-noop: cannot resolve the step: {exc}")
        return 1
    if not step.fixes:
        print(f"fix-noop: step {title!r} declares no `fixes:` in the sidecar; only a fix step can no-op")
        return 1
    try:
        phase = plan.step(step.fixes)
    except KeyError as exc:
        print(f"fix-noop: sidecar `fixes:` does not name a plan step: {exc}")
        return 1
    vj = plan.run_dir / "judge" / phase.slug / "verdict.json"
    if not vj.exists():
        print(f"fix-noop: no judge verdict at {vj}; the judge for {phase.slug} has not recorded one")
        return 1
    try:
        v = json.loads(vj.read_text())
    except json.JSONDecodeError as exc:
        print(f"fix-noop: unreadable verdict.json at {vj}: {exc}")
        return 1
    if v.get("verdict") not in VERDICTS:
        print(f"fix-noop: verdict {v.get('verdict')!r} is not one of the three legal strings; "
              f"the review cannot route this step -- take the refusal path")
        return 1
    if not v.get("counts_declared"):
        print("fix-noop: counts_declared is false; the review cannot route this step -- take the refusal path")
        return 1
    if v.get("certain") != 0:
        print(f"fix-noop: the judge counted certain={v.get('certain')}; take the fix path")
        return 1
    report = cwd / step.report_rel
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(
        f"# Report: {step.title}\n\n"
        f"Verdict: {v['verdict']}\n"
        f"Certain: {v.get('certain')}\n"
        f"Plausible: {v.get('plausible')}\n\n"
        f"The judge reported 0 certain defects on {step.fixes!r}; nothing was changed.\n\n"
        f"## Deviations\n\nnone\n")
    add = subprocess.run(["git", "add", "-f", step.report_rel], cwd=cwd, capture_output=True, text=True, check=False)
    commit = subprocess.run(["git", "commit", "-m", f"docs: {step.slug} no-op, judge reported 0 certain defects"],
                            cwd=cwd, capture_output=True, text=True, check=False)
    if add.returncode != 0 or commit.returncode != 0:
        print(f"fix-noop: report written but the commit failed:\n{add.stderr}{commit.stdout}{commit.stderr}")
        return 1
    print("DONE")
    return 0


def gate(argv: list[str]) -> int:
    """The quality gate, run by Bernstein in the agent worktree before the merge.

    Wired as `quality_gates.pipeline: [{name: tests, required: true, condition: always,
    command_override: bernstein-herdr gate}]`. `command_override` is what makes it run
    verbatim: without it the built-in tests gate composes its own command and returns None
    (skipping the gate entirely) when no Python file changed, whatever `condition` says
    (`gate_runner.py:1613-1634`).

    Exit 1 blocks the merge and is TERMINAL: no retry, no escalation, no quarantine -- the
    branch goes to `refs/graveyard/<sid>-<ts>` (bundle under `.sdd/graveyard/`) and a row lands in `.sdd/runtime/refused_merges.jsonl`
    (measured). So the failing path archives and writes its ledger row too; nothing runs
    after it. That is why a judge step exits 1 on `do not merge` ONLY: every other verdict
    is routing information for `fix-N`, and blocking on it would take `fix-N` with it.
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
    # Bernstein invokes the pipeline TWICE per task, about a second apart, and RESUMES a
    # task whose merge already landed, so without a memo every row, archive and ledger
    # line is doubled and a merged step is re-scored at a HEAD it never merged from. The
    # memo key is (task id, MERGED SHA or worktree HEAD): the same task at the same commit
    # is the same verdict, and a task whose recorded pass is already on the integration
    # branch is finished no matter what its worktree HEAD has become since.
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=wt, capture_output=True, text=True, check=False).stdout.strip()
    cfg_path = plan.run_dir / "bernstein.json"
    cfg = json.loads(cfg_path.read_text()) if cfg_path.exists() else {}
    integration, base_sha = cfg.get("base_ref") or "", cfg.get("base_sha") or ""
    memo_dir = plan.run_dir / "gate-memo"
    passed = memo_dir / f"{task['id']}-merged.json"
    already = short_circuit_sha(wt, memo_dir, task["id"], base_sha, integration)
    if already:
        # A resumed session commits again in the same worktree, so its HEAD is new and the
        # per-head memo misses; without this the step is re-scored against a tree that has
        # already merged, and the second row blocks a task that is done (measured
        # 2026-09-02: `phase-1a` merged at 22:25:39, re-gated blocked=true at 22:33:56).
        print(f"gate: already merged -- task {task['id']} passed at {already[:12]}, which is ahead of the "
              f"frozen base and on {integration}; nothing to re-score. No new row, no new archive.")
        ledger.note(plan.run_dir, f"gate {step.slug} already merged at {already[:12]} on {integration}")
        return 0
    memo = memo_dir / f"{task['id']}-{head[:12]}.json"
    if memo.exists():
        rec = json.loads(memo.read_text())
        print(f"gate: replaying the recorded result for task {task['id']} at {head[:12]} "
              f"(gate already ran at {rec['ts']}); no new row, no new archive")
        print(json.dumps(rec["row"], separators=(",", ":")))
        return int(rec["rc"])

    def remember(row: dict, rc: int) -> int:
        memo.parent.mkdir(parents=True, exist_ok=True)
        rec = {"ts": ledger.now(), "head": head, "rc": rc, "row": row}
        memo.write_text(json.dumps(rec, separators=(",", ":")))
        if rc == 0:
            # The sha this task passed on. Bernstein merges it moments later, which is what
            # makes it the durable key for every gate call after the merge.
            passed.write_text(json.dumps(rec, separators=(",", ":")))
        return rc

    wall, wall_src = wall_seconds(task, wt, step.base)
    common = {"run_id": f"{plan.slug}-{step.slug}", "step": step.slug, "task_id": task["id"],
              "agent": wt.name, "wall_s": wall, "wall_src": wall_src, "evidence": "verified"}
    print(f"gate: step={step.slug} title={task['title']!r} task={task['id']} worktree={wt} head={head[:12]} wall_s={wall} ({wall_src})")

    if step.judges:
        # A judge's only legitimate diff is its review artifacts. Any other tracked
        # change vs the step base means the judge edited code, and the review that
        # sits on top of its own edits is worthless: block before parsing it.
        violations = judge.judge_worktree_violations(wt, step.base)
        if violations:
            row = {**common, "gate": "judge", "blocked": True,
                   "judge_worktree_violations": violations,
                   "reason": "the judge edited files beyond its review artifacts"}
            ledger.row(plan.run_dir, row)
            ledger.note(plan.run_dir, f"gate {step.slug} judge BLOCKED: edited {violations}")
            print(f"gate: BLOCKING -- the judge step changed files beyond "
                  f"{', '.join(judge.JUDGE_ALLOWED)} (the judge edited code): {violations}")
            print(json.dumps(row, separators=(",", ":")))
            return remember(row, 1)
        # A judge verdict ROUTES; it does not block. Only `do not merge` (and a missing
        # review) exits 1. Findings are what the judge is for, and its own diff is the
        # review file: blocking on findings fails the judge TASK, and `fix-N` -- which
        # depends on it -- never spawns. See judge.parse_verdict.
        verdict = judge.record_verdict(plan, step, wt)
        blocked = bool(verdict["block"])
        row = {**common, "gate": "judge", "blocked": blocked, **verdict}
        ledger.row(plan.run_dir, row)
        ledger.note(plan.run_dir, f"gate {step.slug} judge verdict={verdict['verdict']} certain={verdict['certain']} "
                                  f"plausible={verdict['plausible']} blocked={blocked} review_present={verdict['review_present']}")
        print(json.dumps(row, separators=(",", ":")))
        return remember(row, 1 if blocked else 0)

    blocked, f = score(wt, task["title"])
    # ONE ARCHIVE PER ATTEMPT. Keyed by step slug alone, a later attempt overwrote the
    # earlier one's evidence: after a green 14-file gate, `diff.patch` and `numstat.txt`
    # were 0 bytes because a third attempt that had committed nothing wrote over them
    # (finding T, 2026-09-03). Bernstein retries a task IN PLACE under the same id, so the
    # key needs the HEAD too. `latest` is a symlink kept pointing at the newest attempt so
    # a reader still has one stable path.
    dest = plan.run_dir / "reports" / step.slug / f"{task['id']}-{head[:12]}"
    stats = ledger.archive(wt, step.base, dest)
    link = dest.parent / "latest"
    link.unlink(missing_ok=True)
    link.symlink_to(dest.name)
    report = wt / step.report_rel
    if report.exists():
        shutil.copy(report, dest / "report.md")
    row = {**common, "gate": "scorer", "blocked": blocked, **stats, "gate_rc": f["gate"]["rc"],
           "archive": str(dest.relative_to(plan.run_dir)), "commits": f["commits"],
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
        return run_config(repo_root(Path.cwd()), Path(plan) if plan else None, resume="--resume" in rest)
    if cmd == "ready":
        from bernstein_herdr.ready import main as ready_main
        return ready_main(rest)
    if cmd == "scorer":
        from bernstein_herdr.gates.scorer import score
        blocked, f = score(Path.cwd(), _arg(rest, "--step") or "")
        print(f)
        return 1 if blocked else 0
    if cmd == "watch":
        from bernstein_herdr.plan import load_plan, repo_root
        from bernstein_herdr.watch import watch
        root = repo_root(Path.cwd())
        plan = load_plan(root=root)
        kw = {}
        if _arg(rest, "--interval"):
            kw["interval"] = float(_arg(rest, "--interval"))
        if _arg(rest, "--stall"):
            kw["stall_minutes"] = float(_arg(rest, "--stall"))
        return watch(root, plan.run_dir, until_stall="--until-stall" in rest, **kw)
    if cmd == "fix-noop":
        return fix_noop(Path.cwd(), _arg(rest, "--step") or "")
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

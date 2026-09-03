"""Readiness gate: mechanical checks over a plan before any executor starts.

Writes <run>/readiness/ledger.md and <run>/readiness/pins.json (spec, plan, brief
hashes the adapter refuses to start without). Critic rounds are the skill's job;
this file is the part that is a command.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

import yaml

from bernstein_herdr import ledger
from bernstein_herdr.plan import Plan, active_plan_name, load_plan, pinned_hashes

SECTION_CITE = re.compile(r"\b(PLAN|DESIGN|SPEC|spec)\s+(\d+(?:\.\d+)*)\b")
CODE_BLOCK = re.compile(r"```\n(.*?)```", re.S)

#: Bernstein's L0 fast-path rules, copied verbatim from `core/quality/fast_path.py:108-125`
#: (bernstein 3.19.0). `classify_task` matches them against `f"{title} {description}".lower()`
#: (:162) and a hit NEVER reaches an executor: the task is handed to `ruff` instead, which
#: on a non-Python repo dies as `Failed to spawn: ruff` and takes every dependent down with
#: it (measured 2026-09-02: a `phase-1a: lint-fix ...` title lost a whole run in 25 s).
FAST_PATH = [
    (re.compile(r"\b(format|formatting|auto-?format|black|prettier)\b"), "formatting -> ruff format"),
    (re.compile(r"\b(lint|linting|ruff fix|fix lint|autofix)\b"), "lint-fix -> ruff check --fix"),
    (re.compile(r"\b(sort imports?|isort|import order|organiz\w+ imports?)\b"), "import-sort"),
    (re.compile(r"\brename\s+['\"]?\w+['\"]?\s+(?:to|->|=>)\s+['\"]?\w+['\"]?"), "rename-symbol"),
]


def _spec_sections(spec: Path) -> set[str]:
    if not spec.exists():
        return set()
    return {m.group(1) for m in re.finditer(r"^#+\s*(\d+(?:\.\d+)*)\b", spec.read_text(), re.M)}


def check(plan: Plan, run_validation: bool = True) -> tuple[bool, list[str]]:
    lines: list[str] = []
    ok = True
    base = plan.sidecar.get("defaults", {}).get("base", "HEAD")

    def fail(msg: str) -> None:
        nonlocal ok
        ok = False
        lines.append(f"FAIL {msg}")

    plans_dir = plan.root / ".agents" / "build" / "plans"
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", ".agents/build/plans"],
        cwd=plan.root, capture_output=True, check=False,
    ).returncode == 0
    if ignored:
        fail(".agents/build/plans is gitignored; generated plans and briefs would not reach executor worktrees")
    else:
        lines.append("PASS .agents/build/plans is not gitignored")

    try:
        active = active_plan_name(plan.root)
    except RuntimeError as exc:
        fail(str(exc))
    else:
        if active is None:
            lines.append("PASS .agents/build/plans/ACTIVE is absent")
        elif active != plan.path.name:
            fail(f".agents/build/plans/ACTIVE names {active!r}, not selected plan {plan.path.name!r}")
        elif not (plans_dir / active).is_file():
            fail(f".agents/build/plans/ACTIVE names missing plan file {active!r}")
        else:
            lines.append(f"PASS .agents/build/plans/ACTIVE selects {active}")

    # The root checkout is the merge target: every merge-back lands on whatever branch
    # the root has out. A warm-pool spawn runs an agent AT THE ROOT and leaves it on that
    # agent branch, so a second run silently merges everything onto the leftover branch.
    root_branch = subprocess.run(["git", "symbolic-ref", "--short", "-q", "HEAD"], cwd=plan.root,
                                 capture_output=True, text=True, check=False).stdout.strip()
    seed_path = plan.root / "bernstein.yaml"
    seed = (yaml.safe_load(seed_path.read_text()) or {}) if seed_path.exists() else {}
    declared_base = (seed.get("quality_gates") or {}).get("base_ref")
    if not root_branch or root_branch in ("main", "master") or root_branch.split("/", 1)[0] in ("agent", "salvage", "spec"):
        fail(f"the repo root is on {root_branch or 'a detached HEAD'}, not an integration branch (a warm-pool "
             f"spawn leaves it on `agent/*`); every merge would land there -- "
             f"`git -C {plan.root} checkout {declared_base or '<integration branch>'}`")
    else:
        lines.append(f"PASS repo root is checked out on the integration branch {root_branch}")

    # `git diff --name-only <base_ref>..HEAD` in the worktree is the gate's changed-file
    # set. Left at the default `main` it carries every commit the integration branch is
    # ahead by, so the gate judges the branch, not the step (measured: run_config blocked
    # a merge over a file the agent never touched).
    if declared_base == root_branch:
        lines.append(f"PASS bernstein.yaml quality_gates.base_ref = {declared_base} = the checked-out branch")
    else:
        fail(f"bernstein.yaml quality_gates.base_ref is {declared_base!r}, not the checked-out {root_branch!r}; "
             f"the gates would diff the whole branch -- set base_ref to {root_branch!r} and COMMIT bernstein.yaml")

    # `defaults.base` in the sidecar is what every step's diff, allowlist and archive are
    # taken against; a base other than the integration branch shows an earlier step's
    # merged files as this step's changes.
    if base == root_branch:
        lines.append(f"PASS sidecar defaults.base = {base} = the checked-out branch")
    else:
        fail(f"sidecar defaults.base is {base!r}, not the checked-out {root_branch!r}; each step's diff and "
             f"allowlist would be taken against the wrong ref -- set `defaults: {{base: {root_branch}}}` in the .steps.yaml")

    # Codex takes no reasoning-effort flag: `codex exec` reads `model_reasoning_effort`
    # from ~/.codex/config.toml (adapters/codex.py:105-125, argv measured 2026-09-02), so
    # the effort lock lives in a per-machine file OUTSIDE the repo and another machine
    # silently runs the whole plan at `medium`.
    codex_cfg = Path.home() / ".codex" / "config.toml"
    codex_text = codex_cfg.read_text() if codex_cfg.exists() else ""
    if re.search(r'^\s*model_reasoning_effort\s*=\s*"high"', codex_text, re.M):
        lines.append(f"PASS {codex_cfg}: model_reasoning_effort = \"high\"")
    else:
        fail(f'{codex_cfg} does not set model_reasoning_effort = "high"; codex exec takes no effort flag and '
             f"every codex step in this plan would run at the default effort. Add the line and rerun.")

    # Role is the durable dispatch key: a per-step `cli:` is not in Bernstein's plan schema
    # and was measured losing to the role policy on the first retry, while the role policy
    # resolved correctly on every spawn. A role with no policy entry falls back to the
    # seed's top-level `cli:` and whatever model that adapter defaults to.
    policy = seed.get("role_model_policy") or {}
    roles = {s.get("role") for s in plan.steps() if s.get("role")}
    for role in sorted(roles):
        if role in policy:
            lines.append(f"PASS role_model_policy[{role}] = {policy[role]}")
        else:
            fail(f"plan uses role {role!r} with no role_model_policy entry in bernstein.yaml; "
                 f"its cli, model and effort would fall back to the seed default")
    if not roles:
        fail("no step in the plan declares a `role:`; dispatch has nothing to resolve -- "
             "add `role: backend` (or backend2/reviewer) to every step and the matching role_model_policy entry")

    # A step whose title (or description -- Bernstein matches both) hits an L0 rule is
    # never spawned at all; the fast path runs `ruff` in its place.
    for raw in plan.steps():
        text = f"{raw.get('title', '')} {raw.get('description', '')}".lower()
        hit = next(((pat, rule) for pat, rule in FAST_PATH if pat.search(text)), None)
        if hit:
            fail(f"{raw.get('title')!r} matches Bernstein's L0 fast path ({hit[1]}, regex {hit[0].pattern} in "
                 f"core/quality/fast_path.py). The task is routed to ruff instead of an executor and dies "
                 f"`Failed to spawn: ruff`, taking every dependent with it. Reword the title and description "
                 f"(no 'lint', 'format', 'autofix', 'sort imports', 'rename X to Y').")
        else:
            lines.append(f"PASS {raw.get('title')}: no fast-path rule matches title+description")

    # Two open tasks with the same role are BATCHED into one session (`_groups_can_merge`,
    # tick_pipeline.py:113-127, packed by `_pack_affinity_groups_into_batches`:465-491), so
    # two independent steps that share a role never run as two spawns and the DAG's
    # parallel half is a fiction. Steps in the same stage, or in stages with no dependency
    # path between them, are concurrently open.
    stages = plan.data.get("stages", [])
    deps = {st.get("name"): set(st.get("depends_on") or []) for st in stages}
    reach: dict[str, set[str]] = {}

    def ancestors(name: str, seen: frozenset[str] = frozenset()) -> set[str]:
        if name in reach:
            return reach[name]
        out: set[str] = set()
        for d in deps.get(name, ()):
            if d not in seen:
                out |= {d} | ancestors(d, seen | {name})
        reach[name] = out
        return out

    placed = [(st.get("name"), s) for st in stages for s in st.get("steps", [])]
    for i, (stage_a, a) in enumerate(placed):
        for stage_b, b in placed[i + 1:]:
            if not a.get("role") or a.get("role") != b.get("role"):
                continue
            related = stage_a == stage_b or stage_b in ancestors(stage_a) or stage_a in ancestors(stage_b)
            if stage_a == stage_b or not related:
                fail(f"{a.get('title')!r} and {b.get('title')!r} both have role {a['role']!r} and no dependency "
                     f"between their stages ({stage_a!r}, {stage_b!r}), so Bernstein batches them into ONE spawn "
                     f"and one session -- give one of them a different role from KNOWN_ROLES (with its own "
                     f"role_model_policy entry), or make one depend on the other")

    # LINKED WORKTREES SHARE .git/hooks, so a repo-level pre-commit hook runs inside every
    # agent worktree. It ran in the 2026-09-03 acceptance and failed Bernstein's SALVAGE
    # commit twice ("salvage step 2/4 FAILED"), leaving 14 files of finished work as a
    # patch under .sdd/runtime/salvage/ with `branch=None` and no `salvage/*` branch to
    # cherry-pick. An executor's own commit meets the same hook. Fail here, not there.
    hooks_dir = subprocess.run(["git", "rev-parse", "--git-common-dir"], cwd=plan.root,
                               capture_output=True, text=True, check=False).stdout.strip()
    configured = subprocess.run(["git", "config", "--get", "core.hooksPath"], cwd=plan.root,
                                capture_output=True, text=True, check=False).stdout.strip()
    hook_root = plan.root / (configured or f"{hooks_dir or '.git'}/hooks")
    live_hooks = [n for n in ("pre-commit", "commit-msg", "prepare-commit-msg", "pre-push")
                  if (hook_root / n).is_file() and os.access(hook_root / n, os.X_OK)]
    managers = [f for f in ("lefthook.yml", "lefthook.yaml", ".lefthook.yml", "lefthook.toml",
                            "lefthook.json", ".pre-commit-config.yaml", ".husky")
                if (plan.root / f).exists()]
    remedy = (f"  mkdir -p .agents/build/nohooks && git -C {plan.root} config core.hooksPath .agents/build/nohooks\n"
              f"  # after the run: git -C {plan.root} config --unset core.hooksPath\n"
              f"core.hooksPath lives in .git/config, which is untracked, so it never reaches an agent's diff, "
              f"and unlike LEFTHOOK=0/HUSKY=0 it survives both the adapters' filtered spawn env and a mid-run "
              f"`lefthook install` -- a brief that tells an executor to run a setup recipe rewrites the SHARED "
              f".git/hooks under every worktree (measured 2026-09-03).")
    if live_hooks:
        # Only hooks that exist RIGHT NOW under the path git will actually consult are a
        # failure. The old clause also failed on `managers and configured`, which fired
        # exactly when this remedy had been applied -- readiness refused its own fix
        # (finding P). A configured hooksPath with nothing executable in it is the fix
        # working, not a fault.
        fail(f"this repo runs git hooks on commit ({', '.join(live_hooks)}"
             f"{'; core.hooksPath=' + configured if configured else ''}). Linked worktrees share them, so "
             f"they run inside every agent worktree and against Bernstein's salvage commit -- a hook that "
             f"fails there loses the whole step's work (measured 2026-09-03). Point the hooks somewhere "
             f"empty for the run and put it back after:\n{remedy}")
    elif managers and not configured:
        # A NOTE, not a fail: nothing fires yet. But `lefthook install` puts the hooks back
        # into the default .git/hooks at any moment, and the 2026-09-03 run lost 20 files
        # that way -- a brief told the executor to run the repo's setup recipe.
        lines.append(f"NOTE hook manager config present ({', '.join(managers)}) with no hook installed and no "
                     f"core.hooksPath set. Nothing fires today, but any `lefthook install` / `husky install` -- "
                     f"including one a brief asks an executor to run -- reinstalls into the shared .git/hooks "
                     f"mid-run. Set the hooks path before launching the run and unset it after:\n{remedy}")
    else:
        lines.append(f"PASS no commit-time git hooks under {hook_root}"
                     + (f" (core.hooksPath={configured})" if configured else ""))

    v = subprocess.run(["bernstein", "plan", "validate", str(plan.path)], capture_output=True, text=True, check=False)
    lines.append(f"{'PASS' if v.returncode == 0 else 'FAIL'} bernstein plan validate: {v.stdout.strip()[-200:] or v.stderr.strip()[-200:]}")
    ok &= v.returncode == 0

    # Validation commands are replayed on the BASE, which is the same ref for every step
    # of a plan, so the same command answers the same for all of them. The old shape ran
    # `just check` once per step, each in a fresh path-cold worktree: 28 replays, about
    # 20 minutes a pass (measured 2026-09-03, azme recall plan). Now: one answer per
    # (base, command), one worktree per distinct base, created lazily and removed at the
    # end; and no worktree at all when the workspace is checked out at that base and
    # clean, since the tree is then already the base.
    replay_memo: dict[tuple[str, str], int] = {}
    base_trees: dict[str, Path] = {}
    base_tmp: list[tempfile.TemporaryDirectory] = []

    def tree_for(ref: str) -> Path:
        if ref in base_trees:
            return base_trees[ref]
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=plan.root, capture_output=True, text=True, check=False).stdout.strip()
        want = subprocess.run(["git", "rev-parse", ref], cwd=plan.root, capture_output=True, text=True, check=False).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=plan.root, capture_output=True, text=True, check=False).stdout.strip()
        if head and head == want and not dirty:
            base_trees[ref] = plan.root
            lines.append(f"PASS validation replays for base {ref} run in the workspace itself (HEAD is the base, tree clean)")
            return plan.root
        tmp = tempfile.TemporaryDirectory()
        base_tmp.append(tmp)
        wt = Path(tmp.name) / "base"
        subprocess.run(["git", "worktree", "add", "--detach", str(wt), ref], cwd=plan.root, capture_output=True, check=True)
        base_trees[ref] = wt
        return wt

    def replay(ref: str, cmd: str) -> tuple[int, bool]:
        key = (ref, cmd)
        if key in replay_memo:
            return replay_memo[key], True
        r = subprocess.run(["bash", "-c", cmd], cwd=tree_for(ref), capture_output=True, text=True, check=False)
        replay_memo[key] = r.returncode
        return r.returncode, False

    defaults = plan.sidecar.get("defaults", {})
    plan_doc = defaults.get("doc")
    design_doc = defaults.get("design")
    build_spec = defaults.get("spec")
    design_path = plan.root / design_doc if design_doc else plan.root / "docs" / "spec.md"
    # SPEC is the build spec (spec.md beside plan.md) when the sidecar pins one; the
    # lowercase legacy form and an unpinned SPEC still mean the product spec.
    citation_sources = {
        "PLAN": plan.root / plan_doc if plan_doc else None,
        "DESIGN": design_path,
        "SPEC": plan.root / build_spec if build_spec else design_path,
        "spec": design_path,
    }
    citation_sections = {
        label: _spec_sections(path) if path is not None else set()
        for label, path in citation_sources.items()
    }
    for stage in plan.data.get("stages", []):
        owned: dict[str, str] = {}
        for raw in stage.get("steps", []):
            step = plan.step(raw["title"])
            if not step.brief.exists():
                fail(f"{step.slug}: brief missing at {step.brief}; write it, and note that a `brief:` under "
                     f".agents/ must be TRACKED -- an untracked brief does not exist inside the agent's worktree")
                continue
            text = step.brief.read_text()
            lines.append(f"PASS {step.slug}: brief {step.brief.relative_to(plan.root)} ({len(text)} chars, under the 16k cap)"
                         if len(text) <= 16000 else f"NOTE {step.slug}: brief over cap, see below")
            # An executor step with no `files:` has no allowlist, so the scorer cannot tell
            # its work from a stray edit and the merge cannot be scoped. Judge steps own
            # nothing by design (they only write their review).
            if step.judges:
                lines.append(f"PASS {step.slug}: judge step, no allowlist expected (judges {step.judges!r})")
            elif not step.files:
                fail(f"{step.slug}: no `files:` allowlist in the plan step; the scorer has nothing to check a "
                     f"changed file against -- list every path the step may touch under `files:`")
            else:
                lines.append(f"PASS {step.slug}: allowlist {step.files}")
            for g in step.files:
                if not any(True for _ in plan.root.glob(g)) and not re.search(r"[*?\[]", g) and not (plan.root / g).exists():
                    lines.append(f"NOTE {step.slug}: allowlisted path does not exist yet (new file?): {g}")
            for g in step.files:
                for other_title, other_g in owned.items():
                    if g == other_g or fnmatch.fnmatch(g, other_g) or fnmatch.fnmatch(other_g, g):
                        fail(f"{step.slug}: owns {g} which sibling step {other_title!r} also owns ({other_g}); "
                             f"siblings merge in an arbitrary order -- split the files so each path has one owner")
                owned[step.title] = g
            for label, sec in SECTION_CITE.findall(text):
                source = citation_sources[label]
                sections = citation_sections[label]
                if source is None:
                    fail(f"{step.slug}: cites {label} {sec}, but the sidecar pins no source for it (defaults.doc / defaults.spec)")
                elif not source.exists():
                    fail(f"{step.slug}: cites {label} {sec}, but citation source {source} does not exist")
                elif sec not in sections and sec.split(".")[0] not in sections:
                    fail(f"{step.slug}: cites {label} {sec} which does not exist in {source}; "
                         f"fix the citation or add the section (sections present: {sorted(sections)[:8]})")
            # A NOTE, never a fail. The report is evidence, not the work: Codex skips
            # writing one on roughly half its steps whatever the brief says (measured
            # 2026-09-02, `report_mismatch: ["no report file"]` on a step that otherwise
            # held its allowlist and passed), and blocking readiness on the brief's wording
            # buys nothing the scorer does not already record per run.
            if not re.search(r"^##\s*Report", text, re.M) or "Deviations" not in text:
                lines.append(f"NOTE {step.slug}: brief does not require a report file with a Deviations rule; "
                             f"the gate records `report_present` either way -- add a `## Report` section naming "
                             f"{step.report_rel} if you want the evidence")
            else:
                lines.append(f"PASS {step.slug}: brief requires a report at {step.report_rel} with Deviations")
            lines.append(f"PASS {step.slug}: judge step, gate is the verdict parser, no gate command"
                         if step.judges else
                         f"PASS {step.slug}: gate command `{step.gate_cmd}` (base {step.base})")
            # A fix step runs LAST, after a later phase has reddened the tree, and it is
            # scored on the files of the step it fixes. Inheriting `defaults.gate_cmd`
            # there blocked a correct fix three times over a module it never touched
            # (finding W, 2026-09-03: every package ok and golangci-lint 0 issues under
            # the phase's own command). The same argument holds for a judge step whose
            # brief replays a Validation block.
            target = step.fixes or step.judges
            if target and target in {s.get("title") for s in plan.steps()}:
                other = plan.step(target)
                if other.gate_cmd != step.gate_cmd:
                    lines.append(f"NOTE {step.slug}: gate command `{step.gate_cmd}` DIFFERS from the command of "
                                 f"the step it {'fixes' if step.fixes else 'judges'} ({other.slug}: "
                                 f"`{other.gate_cmd}`). A fix or review is scored on that step's scope, and by "
                                 f"the time it runs a later phase has usually left the rest of the tree red -- "
                                 f"give it `gate_cmd: {other.gate_cmd}` in the sidecar unless you meant this.")
            elif step.fixes:
                fail(f"{step.slug}: fixes {step.fixes!r}, which is not a step title in the plan; copy the "
                     f"fixed step's `title:` verbatim into the sidecar `fixes:`")
            elif re.match(r"(fix|polish|repair)-", step.slug) and not step.judges:
                # The check above can only compare what the sidecar declares, and finding W
                # was a plan that declared NOTHING for fix-1: it silently inherited
                # `defaults.gate_cmd` and blocked a correct seven-commit fix three times.
                # A fix step with no `fixes:` is that same plan, so refuse it here.
                fail(f"{step.slug}: looks like a fix step but declares no `fixes:` in the sidecar, so nothing "
                     f"checks its gate command against the step it repairs -- it inherits `{step.gate_cmd}`, "
                     f"which a later phase leaves red by design (finding W, 2026-09-03). Add `fixes: \"<exact "
                     f"title of the step it repairs>\"` and that step's own `gate_cmd:`; if it really spans "
                     f"several steps, name the one whose scope it is scored on.")
            if not re.search(r"^##\s*Items", text, re.M):
                fail(f"{step.slug}: brief lacks an `## Items` section; add the numbered work items the executor must do")
            if len(text) > 16000:
                fail(f"{step.slug}: brief is {len(text)} chars, over the 16k cap (length hurts resolve rate); "
                     f"cut it or split the step")
            if run_validation:
                m = re.search(r"##\s*Validation.*?```\n(.*?)```", text, re.S)
                if not m:
                    fail(f"{step.slug}: brief has no `## Validation` fenced code block; add the exact commands "
                         f"the executor must run, one per line, so they can be replayed on the base")
                else:
                    for cmd in [c for c in m.group(1).splitlines() if c.strip() and not c.startswith("#")]:
                        rc, reused = replay(step.base, cmd)
                        lines.append(f"{'PASS' if rc == 0 else 'RED '} {step.slug} on base {step.base}: `{cmd[:80]}` rc={rc}"
                                     + (" (memoised)" if reused else ""))
            if step.judges and step.judges not in {s["title"] for s in plan.steps()}:
                fail(f"{step.slug}: judges {step.judges!r} which is not a step title in the plan; "
                     f"copy the reviewed step's `title:` verbatim into the sidecar `judges:`")
    # Bernstein content-addresses plan-level `context_files` against the worker's
    # WORKTREE at spawn, before the adapter writes anything into it -- measured
    # 2026-09-02: a brief listed here came back `{"reason_code": "missing"}` in the run
    # journal's context.files_attached for both workers. Only a path in the base tree
    # reaches a worker, so anything else is a silent no-op and fails here.
    for c in plan.data.get("context_files") or []:
        in_base = subprocess.run(["git", "cat-file", "-e", f"{base}:{c}"], cwd=plan.root, capture_output=True, check=False).returncode == 0
        if in_base:
            lines.append(f"PASS context_files: {c}")
        else:
            fail(f"context_files: {c} is not in base {base}; every worker records it `missing` (run-dir briefs included)")
    for s in plan.steps():
        if plan.step(s["title"]).judge == "required" and not s.get("completion_signals"):
            lines.append(f"NOTE {s['title']}: judge required but no completion_signals (the judge gate runs from bernstein.yaml pipeline)")
    for ref, wt in base_trees.items():
        if wt != plan.root:
            subprocess.run(["git", "worktree", "remove", "--force", str(wt)], cwd=plan.root, capture_output=True, check=False)
    for tmp in base_tmp:
        tmp.cleanup()
    return ok, lines


def write(plan: Plan, ok: bool, lines: list[str]) -> Path:
    rd = plan.run_dir / "readiness"
    rd.mkdir(parents=True, exist_ok=True)
    pins = pinned_hashes(plan)
    (rd / "pins.json").write_text(json.dumps(pins, indent=2))
    (rd / "ledger.md").write_text(f"# Readiness {ledger.now()} plan={plan.path.name} ok={ok}\n\n" + "\n".join(f"- {l}" for l in lines) + "\n\nPins:\n" + "\n".join(f"- {k}: {v}" for k, v in pins.items()) + "\n")
    ledger.note(plan.run_dir, f"readiness ok={ok} checks={len(lines)} pins={len(pins)}")
    return rd / "ledger.md"


def main(argv: list[str]) -> int:
    plan_path = Path(argv[argv.index("--plan") + 1]) if "--plan" in argv else None
    plan = load_plan(plan_path)
    ok, lines = check(plan, run_validation="--no-validate" not in argv)
    out = write(plan, ok, lines)
    print("\n".join(lines))
    print(f"\n{'READY' if ok else 'NOT READY'} -> {out}")
    return 0 if ok else 1

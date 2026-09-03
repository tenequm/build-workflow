---
name: build-run
description: "Execute and validate a ready three-stage build unattended. Use /build-run <plan dir>, or /build-run alone inside a workspace, to run the Bernstein DAG, resolve concrete defects through executors, perform whole-branch validation, and optionally open a PR."
---

# build-run

Input: `<plan dir>`, the directory `/build-plan` produced, or nothing. Output:
a validated local workspace branch, `<run>/runs.jsonl`, attempt archives,
judge evidence, and `<run>/ledger.md`. Never edit application code in the
driver session.

Resolving the input:

- `<plan dir>` given: the plan document is `<plan dir>/plan.md`; accept a
  path to `plan.md` itself as the same thing.
- nothing given, inside a workspace (git dir differs from the common dir and
  `<run>/workspace.json` exists for the ACTIVE plan): use the ACTIVE plan and
  its sidecar's `defaults.doc`.
- nothing given, in a primary checkout: list `.claude/worktrees/*` that hold
  an `.agents/build/runs/<slug>/workspace.json`. Exactly one: tell the user
  its path and enter it with the native EnterWorktree tool in path mode, then
  continue. Several: ask which. None: there is no ready build; say so and
  point at `/build-plan`.
- anything else missing on the way (no ACTIVE, no sidecar, no `report.md`,
  readiness not READY): name the missing piece and the `/build-plan` stage
  that produces it, and stop. Never improvise a plan here.

The run is unattended by design. Every decision a human could be asked for
was made in the plan stage: the spec is signed off, witnesses and contracts
are in the tree, every brief was probed. From launch until the DAG ends, do
not ask the user anything; record what you could not resolve in the ledger
and report it at the end. A question that turns out to be necessary mid-run
is a plan-stage defect: log it as `- workflow:` so the retro moves it there.

The moment a skill instruction proves wrong, ambiguous, or is deviated
from - or the user has to intervene where the skill should have sufficed -
append `- workflow: <what and why>` to `<run>/ledger.md`. These lines are
the retro's input for improving the workflow after the run.

Every commit anywhere in this workflow - driver, executor, judge, fix - uses
Conventional Commits: `type(scope): description` with type in feat, fix,
chore, refactor, docs, test, ci, perf. Branch names follow the same shape:
`type/short-description`. No attribution lines or trailers.

Bernstein spawns its own adapters. There is no herdr pane, watcher, or custom
adapter in the loop. Executors commit on `agent/...` branches;
`bernstein-herdr gate` runs in each worktree before merge. Run commands from
the workspace root.

1. Preflight workspace and resolve the plan.

   Require the linked workspace `/build-plan` created. Compare
   `git rev-parse --git-dir` with `git rev-parse --git-common-dir`; refuse when
   they are equal. Require an empty
   `git rev-parse --show-superproject-working-tree` result and an attached HEAD.

   Resolve the machine plan from the plan document: select the sidecar whose
   `defaults.doc` equals `<plan dir>/plan.md`, or use ACTIVE only when its plan
   pins the same document. Refuse multiple or disagreeing matches. Derive
   `<slug>` and `<run>` from that plan.

   Read `<run>/workspace.json`. Require exactly `path`, `branch`, `base`,
   `base_branch`, and `primary`; require the current absolute root to equal
   `path` and the checked-out branch to equal `branch`.

       bernstein doctor
       git symbolic-ref --short HEAD
       bernstein-herdr ready --plan .agents/build/plans/<slug>.yaml

   Doctor findings are advisory. Read readiness output and require READY.
   `bernstein.yaml` from the build-run template must be committed, Codex effort
   must be high, and every role needs a role policy. Require the plan
   directory's `report.md` to exist and its `## Escalations` to list no open
   question; an open escalation means the plan stage did not finish.

2. Write run config.

       bernstein-herdr run-config --plan .agents/build/plans/<slug>.yaml

   This writes `.sdd/runtime/run_config.json` with direct merge, refuses a live
   task server or process for this root, verifies
   `quality_gates.base_ref == <type>/<slug>`, and prints `run with: --port N`.
   It freezes the workspace branch tip in `<run>/bernstein.json` and
   `refs/build/base/<slug>`. Fix only what it names and rerun. Never assume port
   8052.

3. Disable shared hooks before launch.

       mkdir -p .agents/build/nohooks && git config core.hooksPath .agents/build/nohooks

   Linked worktrees share hooks. A hook that rejects an executor or salvage
   commit loses completed work. `core.hooksPath` is untracked and survives the
   adapters' filtered environments. Unset it after validation.

4. Launch DETACHED in its own session. Do not use `--from-plan`.

       python3 - <<'PY' | tee -a <run>/ledger.md
       import os, pathlib, subprocess
       run = pathlib.Path("<run>")
       log = run / "bernstein-run.log"
       env = dict(os.environ, BERNSTEIN_SERVER_URL="http://127.0.0.1:<N>")
       cmd = ["bernstein", "run", ".agents/build/plans/<slug>.yaml",
              "--auto-approve", "--quiet", "--fresh", "--wait", "<budget s>", "--port", "<N>"]
       with log.open("ab") as f:
           p = subprocess.Popen(cmd, stdout=f, stderr=subprocess.STDOUT, env=env,
                                start_new_session=True)
       print(f"- launched bernstein run: wrapper_pid={p.pid} log={log}")
       PY

   `start_new_session=True` is the point of the wrapper: it puts the run in its
   OWN session and process group, so a cleanup that kills the driver's process
   group cannot reach the orchestrator, the task server or the live agents.
   `nohup ... &` does not do this -- it only ignores SIGHUP, leaving the run in
   the driver's group. Record the `wrapper_pid` and log path. Stop deliberately
   with `kill -TERM -<wrapper_pid>`; the negative sign kills the process group.

   `--wait` IS A BUDGET, NOT A CONSTANT. Set `<budget s>` from this plan: the
   sum of the `scope:` buckets along the DAG's critical path, doubled. Fixed
   example numbers have been wrong every time (a 25-minute wait over a run that
   took 1h52m). When the budget lapses the WRAPPER exits; the orchestrator does
   not, so keep watching by step 5's rules rather than reading the wrapper's
   exit as the end of the run.

   AN INTERRUPTED RUN IS NOT RESUMED ONTO AN ADVANCED TIP. Neither a plain
   resume nor `--fresh` is safe once merges from this run are in the branch: a
   resume rebuilt the board as newly open tasks on the already-merged tip, and
   `--fresh` re-runs completed tasks. Two safe moves, and it is the user's call:
   restore `refs/build/base/<slug>` after archiving merged work and run fresh;
   or write a new plan with only remaining work and a new slug. Use
   `<run>/ledger.md` and `runs.jsonl` to identify landed steps.

   `BERNSTEIN_SERVER_URL` is NOT optional. `--port` moves the server only; the
   URL in agent prompts and Claude hook commands otherwise defaults to 8052.
   A stale server answers 401; no server answers connection refused; the log
   scanner can fail the task after its merge landed. Set the variable to the
   printed port exactly.

5. Watch every 30-60 seconds in this order.

       tail -3 <run>/ledger.md
       tail -1 <run>/runs.jsonl
       tail -5 <run>/bernstein-run.log
       bernstein status
       tail -20 .sdd/runtime/spawner.log
       rg -n "liveness_judgment|SIGTERM|Timeout after" .sdd/runtime/spawner.log | tail -5
       rg -n "409|ownership conflict" .sdd/runtime/spawner.log | tail -5

   `bernstein status` has no port option; from the workspace root it reads
   `.sdd/runtime/server.port`. Use `--json` for machine output and
   `--mode expert` for detail.

   Check liveness and scope at runtime. `grace_s=` must match the seed.
   `Timeout after 1800s` on a large step means the patched engine is not active.
   A 409 ownership conflict is a lock wait with 300-second backoff, not a stall.
   Wait for the owner to release.

   A `Total tasks / Failed` block is not terminal when the orchestrator is
   already retrying. The run ends only after that block prints, no Bernstein
   process owns this root, and the board has no runnable task. Ignore its
   `Elapsed: 0s`. Kill any orphan before another run-config.

6. Handle blocked gates and retries.

   A blocked gate refuses this merge. It writes a row to
   `.sdd/runtime/refused_merges.jsonl` and reports unhealthy, but a lifecycle
   retry may already be scheduled even with `gate_repair_enabled: false`.
   Check all evidence before acting:

       tail -1 <run>/runs.jsonl
       cat .sdd/runtime/refused_merges.jsonl
       rg -n "Refusing to merge" <run>/bernstein-run.log .sdd/runtime/spawner.log
       rg -n "retry_or_fail_task" .sdd/runtime/spawner.log | tail -3
       bernstein status

   `verdict=retry ... attempt=N/M` means work continues. Treat only
   `verdict=permanent_fail`, `max_retries_exceeded`, and an idle board as
   terminal.

   THE REFUSED BRANCH IS IN THE GRAVEYARD, NOT IN `salvage/*`. Bernstein moves
   it to `refs/graveyard/<sid>-<ts>`, writes a portable bundle, and deletes
   `agent/<sid>`:

       git for-each-ref --sort=-creatordate refs/graveyard/
       git log --oneline <base>..refs/graveyard/<sid>-<ts>
       ls -t .sdd/graveyard/*.bundle

   Old runs may retain `salvage/<agent>`. A salvage branch alone never meant a
   block; successful merges can salvage untracked leftovers. Trust the blocked
   gate row and `refused_merges.jsonl`.

   A salvage that renamed the workspace branch is a branch-loss event. Check
   whenever a salvage appears and before accepting the result:

       git reflog show --all | rg 'renamed refs/heads/'
       git branch --list '<workspace branch>'
       git log --oneline -5 salvage/<agent>

   If the workspace branch is missing, inspect the salvage tip. Drop only a
   proven `.sdd/` dump, rename the salvage branch back, check it out, and start
   recovery. Anything merged after the rename landed on the wrong branch.

   A MERGED TASK IS NEVER RE-GATED. The pass memo qualifies only when its sha is
   strictly ahead of frozen `base_sha` and on the workspace branch. A blocked
   memo never qualifies. `gate: already merged` creates no row or archive.
   Doing nothing is still scored and blocks.

   `runs.jsonl` is one row per ATTEMPT. A retry reuses its task id. No row means
   the executor died before the gate; inspect the board and spawner log. Each
   attempt archives under `<run>/reports/<step>/<task>-<head>/`; `latest`
   points to the newest. The blocking path archives before review.

   `bernstein quarantine list` is empty after a block; the block is not a
   quarantine. The common cause is an allowlist violation named by the row.
   Once engine retries are spent, mechanically dispatch a fresh executor only
   when the gate or judge names a concrete defect inside existing allowlists.
   Write and commit a fix brief, rerun readiness, and dispatch the fix. Preserve
   the refused commit from `refs/graveyard/...` when useful.

7. Restore a displaced workspace root.

   A warm-pool slot can run at the root, overwrite CLAUDE.md, and switch HEAD to
   `agent/<role>-<id>`. The gate refuses that spawn. On every block check:

       git symbolic-ref --short HEAD
       git status --short
       git checkout <workspace branch> && git checkout -- CLAUDE.md

8. Route judge results.

   A judge gate exits 1 only for the blocking verdict or a missing review.
   Findings normally merge so `fix-N` can read them. The row and verdict.json
   carry verdict, certain, plausible, and counts_declared. `fix-N` takes the
   no-op path only for a legal verdict, declared counts, and zero certain
   defects. Missing, unclear, or undeclared results require a fresh judge.
   Read every fix report; a committed refusal report can itself pass its gate.

9. Apply full autonomy.

   Handle mechanically a refusal whose retry the engine already scheduled, and
   a fix brief to a fresh executor when a gate or judge names a concrete defect.
   When the same step fails twice, a fix would touch outside plan allowlists,
   or a step is blocked with no mechanical move left: mark that step failed
   in the ledger with the gate row and the graveyard ref, let every step that
   does not depend on it continue, and carry the failure into the end report.
   Never wait on the user mid-run. A witness test still red at the final
   `regress` step is a failed outcome, reported by its SPEC 2 number.

10. Never edit `bernstein_herdr` while a run is live. Every gate imports it
    fresh, so a mid-run edit changes the gate under running work.

11. The driver never edits code. Fixes go to a fresh executor with a committed
    brief, file allowlist, validation, and per-item report.

12. Validate the whole branch after the DAG completes.

    Run `polish-new` against the frozen base in `refs/build/base/<slug>`. Apply
    approved polish fixes through fresh executors, not the driver.

    Before accepting a polish round, verify:

    - The comparison base is the frozen ref, not a moving branch name.
    - The diff includes every DAG merge and excludes run evidence.
    - Cleanliness findings name a concrete file and unnecessary construct.
    - Design findings are within the plan document's settled choices.
    - Efficiency findings describe a measurable cost or duplicated pass.
    - Side-effect findings distinguish reads from external mutations.
    - Every proposed code edit fits an existing step allowlist.
    - Every accepted edit has an exact validation command.
    - Every rejected edit is recorded with its reason in the ledger.
    - The driver has not edited application code.

    Stage a blind whole-branch judge from the frozen base:

        git worktree add --detach <run>/judge/branch-N/W refs/build/base/<slug>
        git -C <run>/judge/branch-N/W apply --index <branch diff patch>

    Give a fresh subagent on your own model the detached worktree, the plan
    document, and `skills/build-plan/templates/judge-prompt.md`. Keep it
    read-only except for its review evidence. Require blocking findings only
    and no fixes.

    Give the judge these fixed inputs:

    - The absolute detached worktree path.
    - The frozen base sha and ref.
    - The full applied branch diff.
    - The plan document path.
    - The optional product spec path.
    - Every executor brief and report.
    - The whole-tree gate command.
    - The instruction to attribute files by commit ancestry.
    - The instruction to reproduce certain defects.
    - The instruction to write no application files.

    Turn findings into committed `.agents/build/plans/<slug>/close-N.md` briefs
    and dispatch fresh resolver steps with exact allowlists. Rerun affected
    checks. Repeat polish and blind-judge rounds until a round warrants no
    edits. Remove detached judge worktrees after archiving evidence.

    For each `close-N` round, record:

    - The source finding and file:line.
    - The executor role and task id.
    - The allowed files.
    - The commit sha.
    - Every command and exit code.
    - The next judge verdict.

    Finally run the sidecar's exact `defaults.gate_cmd` on the workspace branch
    and require exit 0. Record every round and command in `<run>/ledger.md`.
    When the plan has witnesses (PLAN 9), list each SPEC 2 outcome with its
    witness tests' final state in the ledger; that list is the run's result.

13. End local.

    Run `git config --unset core.hooksPath`. Keep the validated workspace branch
    local and push nothing. Ask exactly:

    The branch is validated. Open a PR? (default: no)

    Only on explicit yes run `git push -u origin <branch>` and `gh pr create`
    using repo PR conventions. Either way, offer
    `/build-close <path_to_plan_doc>`.

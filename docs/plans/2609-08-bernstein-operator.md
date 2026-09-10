# bernstein_operator: a plugins-only replacement for bernstein_herdr

Status: design settled 2026-09-08, fourth revision. Every claim traced to
engine clone `0a6bf9f2d` by two independent passes (this repo's session +
three adversarial gpt-6-astra reviews, reports archived in session
scratch). Review 2's executed store probe falsified the second revision's
in-DAG routing; review 3 accepted the phase-run architecture and this
revision adds the execution contracts it required (boundary/teardown,
launch transaction, cache prerequisite, judge-ceremony integrity). Implementation
and recording-agent acceptance live in `bernstein_operator/`; see the
[acceptance map](../operator-acceptance.md). `bernstein_herdr` remains in the repository after cutover, per the
operator's explicit retention decision; the new skills use `bernstein_operator`.

## Why now

All 11 of our engine PRs merged upstream by 2026-09-08, the fork is retired,
and the workflow now installs a source build of upstream `main`
(see [the fork decision record](../knowledge/decisions/upstream-first-minimal-fork.md)).
That changed the ground under `bernstein_herdr`: it was written against
v3.19-era Bernstein, and every module works around something the engine did
not do then. A three-way audit of current main showed most workarounds now
have native homes, several herdr assumptions are stale, and one engine
behavior change (gate repair) breaks a documented herdr invariant outright.

## Verified engine semantics that shape the design

Three load-bearing facts, all confirmed by source trace and (the first) by
an executed probe against the real `TaskStore`:

1. **DONE releases the DAG before verification.** `TaskStore.complete()`
   transitions a task to DONE on the worker's claim and immediately calls
   `_revive_blocked_dependents` + `_cascade_unblock_dependency`
   (`task_store_core.py:2383-2385`); readiness accepts DONE
   (`orchestrator.py:1743-1768`); and the tick spawns dependents
   (`claim_and_spawn_batches`, `:2099`) *before* it verifies completions
   (`process_completed_tasks`, `:2108`). Gates, janitor, and merge are
   compensating controls that claw back afterwards - they are not
   barriers. No dependency edge inside a single run can strictly order
   "phase N verified and merged" before "phase N+1 starts".
2. **The engine assigns verdict-driven task creation to the operator.**
   WHY_DETERMINISTIC.md: "no dynamic re-planning during execution... the
   orchestrator will not infer the need." Nothing native dispatches a
   *different* task from a review verdict. (One unrelated conditional
   dispatcher does exist and is default-ON: the pre-stop test follow-up,
   which POSTs an unplanned `qa` task when a surviving agent branch
   touched `src/` without `tests/` - `orchestrator.py:2578,2922`,
   `seed_parser.py:1595`. The template disables it; see below.)
3. **A run self-stops at quiescence - but the stop is a scheduler
   heuristic, not a sealed boundary.** With no open tasks and drained
   agents, the orchestrator settles (default 2 s) and exits
   (`orchestrator.py:2529-2596`). In-run merges are synchronous and
   joined (merge queue held through the operation,
   `merge_queue.py:276-333`; verification futures joined before
   completion processing, `task_lifecycle.py:4949-4987`), so a normal
   merge cannot still be executing when the stop fires. But
   `run_completed` is journaled *before* finalization: `run_quiescence`
   (which measures - and only measures - residual child processes) is
   appended after it (`orchestrator.py:3405-3418`), and the watchdog's
   stand-down check requires `run_completed` to be the journal's *last*
   event (`bootstrap.py:1087`) - which after finalization it never is, so
   the watchdog can restart a cleanly-finished spawner (reproduced by
   probe). The boundary is made real by the driver's teardown contract
   (below), not by the stop alone.

The design consequence: **phase ordering lives between engine runs, not
inside one.** Fact 3 places the boundary there; fact 2 makes the driver
the intended actor at it; fact 1 is why nothing else is sound - and the
driver must own the boundary actively, not just observe it.

## Design principle

1. **The installed package contains only code that must run inside
   Bernstein's process** - gate plugins loaded through the `bernstein.gates`
   entry-point group. Everything driver-side becomes a thin skill script
   over native surfaces (precedent: `plan-lint.sh`, `plan-check.py`).
2. **One engine run per phase; the driver owns the phase boundary.**
   Inside a run, the engine schedules, gates, and merges exactly as
   upstream designed it (optimistic release, compensating verification).
   At the boundary - a native quiescent stop - the driver validates the
   branch, judges the phase, posts the pinned fix run if the verdict
   demands one, and only then launches the next phase's run.

## The declared-but-unwired inventory (why "documented" is not "native")

Verified 2026-09-08; each of these exists in source and executes nowhere on
the plan-run path. Building on any of them repeats the mistake this section
exists to prevent:

- **Lifecycle hook bus**: `LifecycleEvent.POST_MERGE` and the script
  registry exist (`hooks.py:84,360`), but no merge path dispatches any
  lifecycle event - the sole fire site in the tree is `POST_TASK` from the
  external-tracker pipeline (`tracker_pipeline.py:2276`), and the
  orchestrator constructs no hook registry at all.
- **SSE event vocabulary**: the `sse_events.py` factories (`run.completed`,
  `gate_result`, `merge.completed`, ...) have no producer. The wire carries
  only `task_update` and `agent_update` strings (`server_app.py:1052`,
  `task_crud.py:1624`), from in-memory queues with no IDs, no replay, and
  drop-under-pressure semantics. `run_completed` is a journal event, not an
  SSE event.
- **Workflow DSL conditional edges**: `load_workflow_dag()` has no runtime
  caller; `workflow run` prints "DSL workflows aren't executable" for DSL
  manifests (`workflow_cmd.py:403`). The orchestrator's `WorkflowExecutor`
  consumes phase definitions only, discarding node/edge structure.
- **`ReviewGate`**: exported, zero consumers outside its own package.
- **`--approval` / `--merge` CLI flags**: declared with help text
  (`cli/main.py:637-651`), received into the signature, forwarded nowhere.
  The yaml keys validate but never reach the runtime seed config.
- **yaml `pipeline:` with plugin gates**: `_parse_single_pipeline_step`
  raises `SeedError` for any name outside the built-in `VALID_GATE_NAMES`
  frozenset (`seed_parser.py:1946`), and the default pipeline is synthesized
  from built-in flags only. `GateRunner._resolve_pipeline` accepts plugin
  names (`gate_runner.py:1592`) but the yaml path can never deliver them:
  **entry-point gate plugins are unreachable from `bernstein.yaml` on
  current main.**

## What the engine now absorbs (verified on main, 2026-09-08)

| Herdr responsibility | Native mechanism | Evidence |
|---|---|---|
| Warm-pool/salvage branch refusals | #5344: empty slot released, salvage refuses off `agent/*` | `spawner_core.py:4867`, `salvage.py:249`. Caveat: the `WorktreeError` fallback a few lines later still permits an executor at the operator root - keep the root-worktree refusal in the gate. |
| `BERNSTEIN_SERVER_URL` export | #5378: orchestrator publishes its own port to agents | `orchestrator.py:7306` (`setdefault` - a stale inherited value wins, so build-run must launch with a clean env) |
| Same-repo stale-run detection | pid lock + boot-time stale-pid sweep | `bootstrap.py:115`, `server_launch.py:53`. Recorded-PID guards only; keep the orphan-process scan before overwriting config/base refs. |
| Step identity at gate time | `GatePlugin.run(changed_files, run_dir, task_title, task_description)` | `gate_plugins.py:37`, both call sites (`task_lifecycle.py:3162` coalescer, `spawner_merge.py:441` merge-time). Merge-time surrogate carries `session.task_title` with an empty description (`spawner_merge.py:437`); `run_dir` is the agent worktree, and no task/run id or lineage arrives. |
| Scope enforcement (coordination) | `owned_files` -> conflict detector, file locks, claude write-allowlist hook | `plan_loader.py:404`, `spawner_core.py:4937`. Coordination only: native `changed_files` prefers owned files over the observed diff (`gate_runner.py:1776-1809`) and drops deletions - the actual-diff backstop stays ours (see scars). |
| Witness verification | `completion_signals` checked by the janitor | `janitor.py:308`. Shape trap: the loader collapses `{path, contains}` to the path alone (`plan_loader.py:101`) while the janitor needs `value: "path :: needle"` (`janitor.py:2331`) - build-plan must emit the working shape and plan-check must verify *loaded* signals. |
| Brief pinning (observability) | plan `context_files`: content-addressed `(path, order, sha256)` in the run journal | `context_attachments.py:98-159`. Records what existed at spawn; it does not enforce immutability against the sign-off, and per-step `context_files` are not loaded (#3555 territory). Fail-closed pin verification stays ours. |
| Ledger substrates | hash-chained run journal + `.sdd/runtime/gates/<task_id>.json` + review-board diff capture | `journal.py:474`, `gate_runner.py:1944`, `review_board.py:559`. Substrates, not the workflow ledger: gate reports and diffs overwrite per task, and nothing writes build-close's attempt index (see scars). |
| Run state | `bernstein status --json` (supervisor block with stall summary), `runs report --json`, `refused_merges.jsonl` warning at exit | `status_cmd.py:202`, `runs_cmd.py:48`, `run_preflight.py:136` |
| End-of-phase signal | quiescent self-stop + `run_completed` journal event | `orchestrator.py:2529-2596`, `bootstrap.py:1087` - replaces herdr's file-tailing END detection |

Rows from earlier drafts that are **withdrawn**:

- **"Run events via SSE"** - false as written; see the unwired inventory.
- **"Fix dispatch via gate repair"** - the machinery exists
  (`task_lifecycle.py:3225`, default ON, 40-line output tail, preserved
  worktree, then 2 janitor reopens, then quarantine) but is unusable for a
  DAG run: repair fails the original task and mints a new one whose
  `gate_repair_of` lineage no dependency resolver reads
  (`unreachable.py:60-63`), so a successful repair leaves downstream steps
  blocked-by-failed-dep; the repair title `[GATE-REPAIR] {title[:80]}`
  breaks sidecar-by-title; there is no per-step switch. **The template
  sets `gate_repair_enabled: false`.**
- **"Judge routing via in-DAG blocking + `retry_of` revival"** (second
  revision) - falsified by the executed store probe: DONE releases
  dependents before any gate runs (semantics fact 1), `retry_of` is not
  recursive (`unreachable.py:83-92`), reopens re-run the same task id
  without the fix edge, and `POST /tasks` is not idempotent (a repost
  under an existing id silently replaces the row,
  `task_store_core.py:1589-1592`). No variant of in-DAG routing survives
  those four facts together.

Corrected premise carried over: the old template comment about the tests
gate skipping despite `condition: always` was false - `command_override`
has always run first (`gate_runner.py:1677`). The override wiring stays
because it is the native mechanism.

**Response-cache hazard (cutover prerequisite, not a workaround):** the
orchestrator unconditionally constructs a semantic response cache
(`orchestrator.py:601`) and `claim_and_spawn_batches` completes a
single-task batch from a `role:title+description` cache hit with **no
agent spawn and no gate run** (`task_lifecycle.py:2424-2439`); entries
persist in `.sdd/caching/response_cache.jsonl` AND populate in-memory
during a run. There is no disable switch, and half-measures fail: a
per-attempt nonce does not defeat the fuzzy fallback (probe: 0.9936
similarity across different nonces vs the 0.95 threshold), pre-launch file
deletion does not stop same-run population, and the `verified` flag is
computed before merge success (`task_lifecycle.py:3819`), so a
merge-failed attempt can seed a "verified" entry that later completes a
reopened task unexecuted. **Disabling this path is a prerequisite for
cutover** - upstream flag (enabler #4) or the minimal local patch on the
source build (fork-if-needed, operator decision 2026-09-08). The positive
delivery predicate additionally parks any task that completed without an
attributable executed attempt.

## What stays ours, and why (each verified against main)

- **`run_config.json` write**: the only ingestion path for
  `merge_strategy: direct` (`orchestrator.py:7262-7271` reads it; the CLI
  flags and yaml keys are dead - see inventory). Two keys matter:
  `merge_strategy`, `budget_usd`. Self-retiring if the flag wiring lands
  upstream.
- **Free port per run**: `--port` hard-defaults to 8052
  (`cli/main.py:816`), `_wait_for_server` trusts any 200 from `/health`
  without identity (`server_launch.py:392`). Pick a free port AND verify
  server identity/credentials after launch; handle the bind race.
- **Frozen base `refs/build/base/<slug>`**: worktrees branch from live HEAD
  (`git worktree add -b`, no start-point - `git_pr.py:737`), gates diff a
  static `base_ref: "main"`. The recorded run-start sha is read by the
  review-board projection but never used as a scoring baseline - judges
  must diff a ref frozen at run start. The ref is write-once for the
  build; each phase additionally records its own start tip, so the
  cumulative judge range and a per-phase delta are both derivable.
- **Gate memoization, content-bound**: the pipeline fires from two call
  sites per task and plugin gates are excluded from the native cache
  entirely (`gate_runner.py:1867`). The memo binds
  `(title, HEAD, comparison base, policy version)` AND is consulted only
  on a clean tree (no staged/unstaged/untracked deltas beyond declared
  evidence, separately hashed) - HEAD alone cannot see a mutated index or
  working tree, and a stale PASS must not be reusable against changed
  inputs.
- **Per-attempt evidence**: native review-board diffs
  (`review/diffs/<task_id>.diff`) and gate reports overwrite per task.
  Per-attempt archive under `<run>/reports/<step>/` stays, keyed by an
  attempt id (not just `(slug, head)` - same-HEAD re-scores must not
  clobber), with atomic writes.
- **Phase-level blind judge**: the deployed per-task surfaces are shallow
  (12k-char diff to a cheap cross-provider model, approve/request_changes).
  `review_pipeline` has richer library paths but none is wired as a
  phase-level blind review with counted findings against a brief. The
  judge is now a **driver-side ceremony** (below), not an in-DAG task.
- **Workflow-specific admission**: citations vs spec/plan, sign-off sha
  pin, validation replay on the frozen base, `core.hooksPath` check (zero
  occurrences upstream), 40 GB disk floor (native floor is a 1 GiB spawn
  refusal, `defaults.py:189`), environment/dispatch manifests from
  `ready.py`.
- **Watch + resume**: the watch loop polls `status --json` /
  `runs report --json` / the journal (no SSE dependency); `run_completed`
  means *scheduler closure*, and the driver's own completion predicate
  (every expected step landed, verdict reconciled, obligations empty)
  decides success. Plan-run resume stays custom: nothing native prunes
  already-landed steps (explicit-plan bootstrap skips session resume,
  `bootstrap.py:1275`, and relaunch wipes `tasks.jsonl`,
  `server_launch.py:76`), and resume must reconcile journaled fix
  obligations - including a fix already claimed, done, or closed when
  recovery starts.

## The package: one gate plugin (scorer)

`bernstein_operator/` - a Python package whose entire contents are:

```
pyproject.toml            entry point: bernstein.gates -> scorer
src/bernstein_operator/
  scorer.py               the scripted scorer as a GatePlugin
  shared.py               sidecar-by-title, diff/base logic, memo, archive
```

The judge plugin from earlier drafts is **deleted**: judging is a
driver-side phase ceremony, so nothing judge-shaped needs to run inside
Bernstein's process. The package shrinks to the one check that must run at
the engine's merge gate. Target: 250-350 lines. The functions are
deterministic and unit-testable, but they run subprocesses against mutable
worktrees - the command runner enforces its own timeout and cleanup, never
chdirs globally (both call sites run gates under `asyncio.gather`), and
treats a diff failure as a failure, never as an empty diff.

**Configuration bridge (blocking prerequisite).** Because the seed parser
rejects plugin names in `pipeline:` (see inventory), the plugin cannot be
declared from `bernstein.yaml` today. Two tracks:

1. **Upstream PR** (the real fix, small): make
   `_parse_single_pipeline_step` consult the gate-plugin registry, with a
   source-build acceptance test. Proceeds in its own workstream; if it
   stalls, the source build carries a minimal local patch (operator
   decision 2026-09-08 - fork-if-needed, not fork-by-default).
2. **Bridge until merged**: keep today's mechanism - the built-in `tests`
   gate's `command_override` invoking the scorer script - unchanged.

**Scorer policy** (nothing upstream has any of it): run the sidecar's real
gate command with the per-run lint cache; deleted-test and
unjustified-suppression scans; report-accuracy check against the measured
gate; refusal receipts; commit-count; root-worktree refusal. Rules:

- **`condition: always`, never `any_changed`**: an unmatched condition
  yields `status="skipped", blocked=False` (verified), which would wave
  through no-commit and deletion-only attempts. Unknown or unresolvable
  titles fail closed.
- **Fork-point diffs, pre-landing only.** Content scans diff from
  `git merge-base HEAD <branch>` while the attempt is unmerged. After
  landing, the merge base becomes the task HEAD and the diff reads empty
  (reproduced), so the landed-SHA ancestry check survives unchanged: a
  known-landed PASS is deduplicated by ancestry, never re-derived.
- **The native `changed_files` is a hint, never the authority.** Compute
  the changed set independently (deletions, renames, untracked evidence
  included); the allowlist check runs on the observed set.
- **Refusal receipts are routing classes** (`scope_exceeded`,
  `underspecified`, `blocked_on_dependency`, `awaiting_operator`) that
  park the step for the driver; only mechanical failures end with an
  imperative fix summary in the output tail.

## Phase execution: one engine run per phase

The plan file still authors everything up front - every phase's executor
steps, the judge brief, and every fix brief as a **complete frozen task
specification** (role/model/effort, owned files, completion signals in the
working shape, brief, sidecar identity) - validated at readiness. Execution
is a driver loop over phases:

1. **Launch phase N as a transaction.** The driver POSTs phase N's
   executor tasks *directly* to the task server with the full frozen
   payload - the native plan-post helper silently drops
   `completion_signals` (`planner.py:43-124` builds the body field by
   field; verified by probe), so `bernstein run --from-plan` is not the
   launch path. Fresh unique `BERNSTEIN_RUN_ID` per run, journaled
   against the workflow attempt before launch; no explicit task ids
   (server-assigned, with a durable logical-step -> server-id map).
   The transaction's entry points are explicit: start the server alone
   (`serve` / `supervised_server`), POST and verify (stored payloads and
   full task inventory equal the posted set), then start the spawner
   (`server_launch._start_spawner`) - never a normal goal/plan bootstrap
   racing the POSTs, whose empty-queue fallback injects a manager task
   (`bootstrap.py:468,1319`). Task-ingress isolation is part of the
   transaction: bootstrap's workflow importer turns root
   `TODO.md`/`TASKS.md`/`.plan` items into OPEN tasks
   (`workflow_importer.py:105-124`) and the running orchestrator ingests
   backlog on normal ticks (`orchestrator.py:1652`), so the workspace
   carries no importable files, backlog stays empty, and the inventory
   check runs before and during the run - absence of root files is a
   precondition, the inventory check is the enforcement. Quarantine is
   preflighted: entries persist per exact title across runs
   (`quarantine.py:122-137`) and skip scheduling without terminalizing,
   leaving an OPEN-but-unschedulable stall - a quarantined expected step
   is a park, surfaced before launch.
2. **Run to the stop, then tear down.** Inside the run the engine
   schedules, the scorer gates every merge, intra-phase deps are
   optimistic by design (anything needing verified-before-start is a
   phase split). At the stop the driver executes the boundary contract:
   wait for the *identified* orchestrator process to exit AND the
   journal to carry `run_quiescence` (not just `run_completed`);
   resolve residual child processes (a survivor is a park, not a
   shrug - quiescence only measures); positively stop the watchdog,
   CLI supervisor, and task server (the scheduler's exit stops neither,
   and a new server on a new port coexists with a live old one in the
   same `.sdd`); never use `bernstein stop`'s soft drain (its
   `DrainConfig` defaults auto-commit AND auto-merge on, and its merge
   phase can land rejected branches outside the scorer path,
   `drain.py:49-66,514-551`); then capture and pin the branch tip.
3. **Reconcile with a positive delivery predicate.** Scheduler closure is
   not success. For every frozen logical step: map step -> actual
   attempt/task -> scorer PASS for that exact content -> delivered
   commit -> ancestry in the pinned tip. Absence of any link parks;
   unexpected tasks or merges park; a refusal class parks with its
   reason. `runs report --json`, the journal, gate reports, and
   `refused_merges.jsonl` are the evidence sources, not the predicate.
   Archive the run's native evidence into workflow-owned storage now -
   native retention prunes beyond 20 run dirs (`defaults.py:589`), and a
   multi-phase build burns one per phase plus every fix.
4. **Judge the phase (driver-side ceremony).** Stage the branch diff
   from `refs/build/base/<slug>` in a detached worktree placed inside
   the workflow `<run>` tree (never under `.sdd/worktrees`, whose dirty
   dirs the next boot can move as WIP, `orchestrator.py:4159-4198`).
   Assert the staged tree exactly equals the pinned tip before the
   judge starts; record and reap the judge's process group on
   success/timeout/crash; after the verdict, re-verify the staged tree
   is unchanged and the integration ref still names the pinned tip -
   any drift invalidates the review. Review-only enforcement compares
   the judge's deltas against the *staged input* (the old frozen-base
   comparison would flag the staging commit itself), allowing declared
   evidence only. Verdict validation keeps the full herdr contract
   (counts declared, structured/prose agreement, evidence checks) -
   moved into driver code, not weakened into one string match. The
   verdict archives per attempt with the exact reviewed range (base
   sha, pinned tip sha). No engine run launches while a judge lives.
5. **React** - a pure function of the archived attempt receipt (never a
   `latest` pointer), journaled before acting, with explicit precedence:
   `do not merge` parks the build; otherwise `certain > 0` posts the
   pinned fix as its own mini-run - the immutable verdict bytes and
   receipt travel to the fix as pinned, hash-bound inputs (the old
   in-branch review path no longer exists) - and returns to step 2 for
   the new range; a clean verdict releases phase N+1. A malformed or
   missing verdict re-runs the judge once, then parks; a stale verdict
   never triggers a fix after an unrelated later failure. The loop
   carries a whole-build bound: attempts, spend (per-run budgets reset
   every launch - the workflow ledger holds the build-level cap), and
   wall clock.
6. **Crash safety**: one driver writer; every launch and POST journaled
   before it happens; recovery is read-before-act against server AND
   infrastructure state (does the run/server/process already exist?) -
   never a blind repost (`POST /tasks` is not idempotent; a reused
   explicit id silently replaces the row). Native WAL/WIP from an
   interrupted run is preserved and reconciled before any state reset.

Scope note: the judge range `(build base, pinned tip)` is a cumulative
review by design - earlier-phase findings can resurface. A finding whose
files the current phase's pre-briefed fix cannot touch parks for the
operator instead of silently widening the fix. The final regression phase
retains the whole-tree validation duty: per-worktree PASSes plus landed
commits do not prove the combined tree passes.

## Skill-side changes (scripts and config, no package code)

- **build-run**: write the 2-key `run_config.json`; pick a free port and
  verify server identity after launch; freeze `refs/build/base/<slug>`
  (write-once) via `git update-ref` and record each phase's start tip;
  check `base_ref` matches the checked-out branch; run with the
  response-cache path disabled (prerequisite patch/flag). Watch is a poll
  loop (`status --json` supervisor stall block + `runs report --json` +
  journal tail), with the existing disk/no-start/orchestrator-death
  checks kept. Phase loop, launch transaction, boundary/teardown
  contract, delivery predicate, judge ceremony, and reaction procedure as
  above. Resume reconciles journaled obligations against actual
  server/journal/infrastructure state before releasing anything.
- **build-plan**: emit `files:` (-> `owned_files`), `completion_signals:`
  with `file_contains` in the working `value: "path :: needle"` shape, and
  briefs pinned per step; split any strict verified-before-start
  dependency into separate phases; keep parallel steps on distinct roles
  (the native batcher groups same-role tasks, `max_tasks_per_agent`
  defaults to 2, and no yaml key reaches it - verified); fold the
  workflow-specific admission checks into `plan-check.py`, layered on
  native `bernstein plan validate` (remembering `dry-run --plan` exits 0
  on load failure, #3550) and comparing declared vs loaded signals.
- **bernstein.yaml template**: `gate_repair_enabled: false` (see withdrawn
  row); `flaky_detection: false` (verified: deselect args are appended
  after `command_override`); `orchestration.test_followup: false` and
  `BERNSTEIN_TEST_FOLLOWUP` cleared from the launch env (default-ON
  conditional task creation at the quiescence check - an unplanned,
  signal-less `qa` task the inventory rule would only park);
  `BERNSTEIN_JANITOR_REOPEN_MAX=0`, because a reopened step that merges
  after an earlier attempt already merged delivers one step twice, and
  repair belongs to the judged fix mini-runs (measured 2026-09-10).
- **Retired assumptions**: "exit 1 is TERMINAL" is deleted from every
  skill and docstring; the gate is documented as resume-idempotent.

## Retained scars (each nearly lost in earlier drafts)

1. Landed-SHA ancestry check (merge-base validity ends at landing).
2. Actual-diff backstop over native `changed_files`.
3. Root-worktree refusal (cold-spawn fallback still reaches the root).
4. Memo bound to content, not just `(title, HEAD)`; clean-tree rule; a
   PASS memo is evidence of scoring, not of landing - resume never prunes
   on it alone.
5. A thin ledger writer (attempt index + driver decisions + fix
   obligations + launch receipts) feeding build-close's
   `runs.jsonl`/`ledger.md` contract - `ledger.py` slims into build-run's
   scripts, it does not vanish. build-close reads both native `.sdd/runs`
   evidence and the workflow ledger, and cleanup preserves them.
6. Frozen-policy enforcement: plan/sidecar read from the frozen ref,
   readiness pin drift detection (spawn-time hashes observe, they do not
   enforce).
7. The environment/dispatch manifest and readiness checks from `ready.py`.

## Deleted outright, with the native reason

`task_for_worktree`/`team.json` heuristics (replaced by driver-admitted IDs;
the native merge call site supplies a surrogate task ID, so a run-bound
task-store lookup is still required),
`fix-noop` and in-DAG judge/fix steps (phase-boundary driver loop),
`judge.py` as a gate plugin (driver-side ceremony),
`merged_ahead`/`short_circuit_sha` complexity (shrinks into the memo +
ancestry check), warm-pool/salvage refusals (#5344, minus the
root-worktree case), stale-pid sweep (native), `BERNSTEIN_SERVER_URL`
plumbing (#5378), file-tailing watch and END detection (poll + native
quiescent stop), `triage` (driver reads native JSON), `fake.py` (the
plugin is testable without an adapter; launch-to-merge contract coverage
migrates to the acceptance list, it is not dropped with the fake).

## Upstream enablers (separate workstream; each deletes a workaround)

Filed and tracked outside this plan. Package *development* proceeds
independently of all of them. Workflow *cutover* requires four things:
plugin reachability (#1, with the local-patch fallback), effective
response-cache neutralization (#4, likewise), local-only merge-back (#7),
and a quiescence self-stop that counts merged work (#8) - fail-closed
prerequisites, not conveniences.

1. **Plugin-aware `pipeline:` validation** in the seed parser - unblocks
   the entry-point cutover (bridge: `command_override`).
2. **Wire `--approval`/`--merge` through to runtime config** - retires the
   `run_config.json` write.
3. **A yaml key for `max_tasks_per_agent`** - retires the role-separation
   constraint in build-plan.
4. **A disable flag for the response cache.** Neutralizing this path is a
   cutover prerequisite; until the flag lands the source build carries
   the minimal local patch. (A content-bound cache key alone is not a
   substitute - the bypass path must execute the scorer, not merely miss
   more often.)
5. **Forward `completion_signals` in `_post_task_to_server`** - a live
   upstream defect: plan-file witnesses are silently dropped at POST
   today (`planner.py:43-124`), which affects the *current* workflow too.
   Our driver-direct POSTs sidestep it; every `--from-plan` user hits it.
6. **Fix the watchdog stand-down check** - `events[-1] == "run_completed"`
   never matches after finalization appends `run_quiescence`
   (`bootstrap.py:1087`), so a cleanly-finished spawner can be restarted.
   Our teardown contract sidesteps it; the fix is a membership check.
7. **Disable automatic fetch/rebase/push for local builds.** Native
   `spawner_merge.py` calls `safe_push` after merge-back. Its fetch/rebase
   changes commit identity and its push violates the local completion contract.
   Until upstream exposes this control, the source patch makes `safe_push`
   return before any Git I/O when `BERNSTEIN_OPERATOR_LOCAL_ONLY=1`.
8. **Count a merged task as terminal in the quiescence self-stop.** The task
   store archives a verified, merged task to `CLOSED`
   (`task_store_core.py:2409`), and the orchestrator's self-stop gate reads
   only `done`/`failed` from a `fetch_all_tasks` call whose default statuses
   omit `closed` - so a run whose every task merged idles forever, never
   journaling `run_completed`/`run_quiescence`. Measured on the first real
   build, 2026-09-10; the recorded-executor acceptance run reaches its
   quiescent tick while the task is still `done`, which is why the suite
   never saw it. The engine already treats `closed` as terminal for
   dependency release (`orchestrator.py:1763`), so the source patch adds the
   same status to that one check.

## Acceptance evidence before the revision is called settled

1. An installed entry-point plugin, declared in a real parsed
   `bernstein.yaml`, executes at both gate call sites; a missing/broken
   plugin fails admission (post-enabler-#1).
2. Phase N+1 tasks do not exist on any server until the driver releases
   them: a paused judge ceremony, a parked `do not merge`, and a pending
   fix each provably hold the boundary - including across a driver crash
   at every stage of the reaction procedure (journal, POST, receipt).
   The boundary holds against the infrastructure too: a run completes
   through `run_completed` AND `run_quiescence`, the watchdog poll
   interval elapses with no restart and no second writer; two phases on
   distinct ports in one workspace cannot cross-write; teardown lands
   nothing (no soft-drain auto-merge); a residual child process parks
   the boundary instead of judging past it.
3. The response-cache path is provably dead: cache populated *during* a
   phase, a similar nonce-bearing task, a recovery restart, and a
   merge-failed reopen all still execute the scorer (in addition to the
   preloaded-entry case).
4. Refusal classes, malformed verdicts, and `do not merge` have distinct
   tested outcomes; a stale verdict cannot trigger a fix after an
   unrelated later failure (reactions bind to immutable attempt receipts,
   not a `latest` pointer).
5. Unauthorized change alongside an owned file, deletion-only work,
   uncommitted changes, and no-commit attempts cannot bypass the scorer
   (`condition: always` + observed-diff authority).
6. The working `file_contains` shape is tested through load AND janitor
   evaluation; plan-check rejects the broken shape.
7. Same `(title, HEAD)` with a dirty tree, changed evidence, or changed
   policy cannot reuse a stale PASS or overwrite an earlier attempt's
   archive; landed evidence survives integration advancing.
8. Driver death longer than the quiescence window, late watcher attach,
   server death, no-start, and low disk all produce correct terminal
   behavior; `run_completed` alone is never reported as build success.
9. Resume after a crash reconciles journaled obligations against server
   AND infrastructure state - including a fix already claimed, done, or
   closed - creating nothing twice and losing nothing.
10. The launch transaction is exercised end to end: the driver-direct
    POST retains `completion_signals` and attempt identity in the stored
    server task; an importable `TODO.md` naming future-phase work never
    becomes schedulable; a quarantined expected title parks the phase;
    an empty workspace with no prior session injects no manager task;
    with `test_followup` disabled, a source-only phase schedules no
    native follow-up task.
11. Judge-ceremony integrity: mutating an application file in the staged
    tree, moving the integration ref mid-review, and crashing the judge
    with a live child each invalidate the review; staged-tree equality
    and immutable fix-input delivery are asserted.
12. A build with repeated repairs respects the whole-build spend/attempt
    bound, survives quarantine interactions, and retains all
    build-close-required evidence past 20 native runs.
13. build-close reads the new evidence layout and preserves required
    records before workspace cleanup; the release updates both
    `plugin.json` files and all three skills in one cut (including both
    judge-prompt template copies, purged of gate-cross-check and
    merge-to-trigger-fix assumptions).

## Migration

Build `bernstein_operator/` alongside `bernstein_herdr/` (enabler #1
proceeds in its own workstream, with the local-patch fallback), move the
herdr judge logic into build-run's phase ceremony, port the herdr test
scenarios whose invariants survive (most hardening tests die with the code
they hardened; the ones in the acceptance list above do not), cut the
skills over in one release, and keep `bernstein_herdr/` in the repository.
Retaining the old package is intentional, including after acceptance; it is
not part of the new skills' runtime. The uv install line changes only in the
`--with` path. CI is deferred; local checks and acceptance tests remain required.

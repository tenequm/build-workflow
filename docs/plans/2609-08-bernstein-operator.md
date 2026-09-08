# bernstein_operator: a plugins-only replacement for bernstein_herdr

Status: design settled 2026-09-08, not yet built. Supersedes nothing yet;
`bernstein_herdr` remains the shipped companion until this lands.

## Why now

All 11 of our engine PRs merged upstream by 2026-09-08, the fork is retired,
and the workflow now installs a source build of upstream `main`
(see [the fork decision record](../knowledge/decisions/upstream-first-minimal-fork.md)).
That changed the ground under `bernstein_herdr`: it was written against
v3.19-era Bernstein, and every module works around something the engine did
not do then. A three-way audit of current main (run-config/resume/ports,
gate/judge pipeline, observability - 2026-09-08, this repo's session
history) showed most workarounds now have native homes, several herdr
assumptions are stale, and one engine behavior change (gate repair) breaks
a documented herdr invariant outright.

## Design principle

Two rules, both taken from Bernstein's own architecture:

1. **The installed package contains only code that must run inside
   Bernstein's process** - gate plugins loaded through the `bernstein.gates`
   entry-point group. Everything driver-side becomes a thin skill script
   over native surfaces (precedent: `plan-lint.sh`, `plan-check.py`).
2. **Contingency is a reaction, not plan topology.** Upstream's plan format
   is deliberately branch-free; conditional behavior lives in deterministic
   lifecycle reactions that create or reopen tasks at runtime (reviewer ->
   fix task, blocked gate -> gate repair, failure -> escalated retry). Our
   judge routing adopts that idiom instead of encoding it in the gate.

## What the engine now absorbs (verified on main, 2026-09-08)

| Herdr responsibility | Native mechanism | Evidence |
|---|---|---|
| Warm-pool/salvage branch refusals | #5344 (in v3.19.1): empty slot released, salvage refuses off `agent/*` | `spawner_core.py:4863`, `salvage.py:242` |
| `BERNSTEIN_SERVER_URL` export | #5378: orchestrator publishes its own port to agents | `orchestrator.py:7306` |
| Same-repo stale-run detection | pid lock + boot-time stale-pid sweep | `bootstrap.py:115`, `server_launch.py:53` |
| Step identity at gate time | `GatePlugin.run(changed_files, run_dir, task_title, task_description)` | `gate_plugins.py:37`, invoked both call sites; merge-time surrogate carries the title (`spawner_merge.py:435`) |
| Scope enforcement | `owned_files` -> conflict detector, file locks, and (claude adapter) an in-session write-allowlist hook gate | `plans.md`, `capabilities.md`, `failure-taxonomy.md` (`scope_violation`) |
| Witness verification | `completion_signals` (`test_passes`, `path_exists`, `file_contains`) checked by the janitor | `quality-pipeline.md` |
| Brief pinning | plan `context_files`: content-addressed `(path, order, sha256)`, recorded in the run journal | `plans.md` "context files" |
| Ledger | hash-chained run journal + `.sdd/runtime/gates/<task_id>.json` + review-board diff capture | `review_board.py`, `gate_runner.py:1941` |
| Fix dispatch for mechanical failures | gate repair (default ON): `[GATE-REPAIR]` task resumes the same worktree, prompted with the gate's output tail; then up to 2 janitor reopens, then cross-run quarantine; cascade escalation feeds off janitor failures | `task_lifecycle.py:3225`, `:5127` |
| Run events | SSE `/events` with the exact event vocabulary herdr's watch synthesized | `status_events.py`, `sse_events.py` |
| Run state | `bernstein status --json` (supervisor block), `runs report --json`, `refused_merges.jsonl` warning at exit | `status_cmd.py`, `runs_cmd.py`, `run_preflight.py` |

Corrected premise: the old `bernstein.yaml` template comment claimed the
built-in tests gate skips despite `condition: always` without
`command_override`. False even at v3.19.1 - `command_override` has always
run first (`gate_runner.py:1677`). The override wiring stays because it is
the native mechanism; the justification comment goes.

## What stays ours, and why (each verified ABSENT upstream)

- **`run_config.json` write**: the only way to get `merge_strategy: direct`.
  The `--approval`/`--merge` CLI flags are declared but never forwarded;
  the yaml keys validate but are never parsed into the runtime seed config.
- **Free port per run**: `--port` hard-defaults to 8052 with no free-port
  search; a foreign repo's server on 8052 answers `/health` and silently
  absorbs the run.
- **Frozen base `refs/build/base/<slug>`**: gates diff a static branch name,
  worktrees branch from live HEAD, and the recorded run-start sha is never
  read back. Judges must diff a ref frozen at run start.
- **Gate memoization**: the pipeline still fires from two call sites per
  task (verification-time coalescer + merge-time direct call); the native
  gate cache misses across them whenever `owned_files` is set, and plugin
  gates are excluded from the cache entirely.
- **Per-attempt evidence**: the native review-board diff capture is keyed
  `(run, task)` and overwrites; only hashes survive in the journal. Finding
  T (a later empty attempt clobbering a green attempt's evidence) would
  recur.
- **Phase-level blind judge**: upstream review surfaces are per-task and
  shallow (12k-char diff to a cheap cross-provider model, approve /
  request_changes). A fresh full agent blind-reviewing a whole merged phase
  against a brief, with counted findings, has no native counterpart.
- **Workflow-specific admission**: citations vs spec/plan, sign-off sha
  pin, validation replay on the frozen base, `core.hooksPath` check
  (zero occurrences upstream - they install their own hooks and never
  inspect the operator's), 40 GB disk floor (native floor is 1 GB).
- **Headless watch/resume**: the SSE stream exists but only the TUI
  consumes it - no CLI follower, no stall timer, no exit-on-run-end.
  Native resume is goal-path only and all-or-nothing; plan runs always
  re-enqueue every step.

## Why not full native for judge routing (decision record)

The two native surfaces that would carry it are dead code, verified
2026-09-08: the Workflow DSL's conditional edges have zero runtime
consumers (nothing in `core/orchestration/` or `core/tasks/` loads a
`WorkflowDAG`; the DSL backs `workflow validate/list/show` only), and
`ReviewGate` is library-only. `bernstein workflow run` executes a different
manifest flavor (#1108 `WorkflowRunner`) that bypasses the task server,
janitor, and gate pipeline. Building on documented-but-unexecuted paths is
not "native". Revisit if upstream wires conditional edges into task
readiness - the docs signal that intent.

## The package: two gate plugins

`bernstein_operator/` - a Python package whose entire contents are:

```
pyproject.toml            entry points: bernstein.gates -> scorer, judge
src/bernstein_operator/
  scorer.py               the scripted scorer, as a GatePlugin
  judge.py                verdict parse; blocks ONLY on "do not merge"
  shared.py               sidecar-by-title, fork-point diff, memo, archive
```

Target: 300-400 lines total, pure functions of
`(changed_files, run_dir, task_title)`, unit-testable without any adapter
or fake. Installed exactly as today:
`uv tool install <clone> --with ./bernstein_operator`.

**scorer.py** keeps the policy nothing upstream has: run the sidecar's real
gate command with the per-run lint cache; deleted-test and unjustified-
suppression scans; report-accuracy check against the measured gate;
refusal receipts; commit-count. Changes from herdr:

- **Fork-point diffs.** Every content scan diffs from
  `git merge-base HEAD <branch>`, fixing the moving-base defect (both our
  sidecar's live-branch base and upstream's `base_ref..HEAD` are wrong in
  one race direction each; the fork point is wrong in neither). The
  allowlist check consumes the natively supplied `changed_files`
  (`owned_files`-derived) and treats its own diff as the backstop for
  adapters without write hooks (codex).
- **Memo keyed `(title, HEAD)`** absorbs the double invocation; the
  "only a PASS memo short-circuits" and "strictly ahead of the frozen
  base" rules carry over unchanged (they are scars, not speculation).
- **Per-attempt archive** under `<run>/reports/<step>/<title-slug>-<head>/`
  with a `latest` symlink, unchanged in spirit.
- **The output tail is a repair prompt.** Gate repair feeds the last ~40
  lines of gate output to the repair executor verbatim, so the scorer ends
  its output with a deliberate, imperative failure summary.

**judge.py** shrinks: parse `verdict.json` shape (three legal strings,
counts declared), enforce review-only (tracked changes beyond review
artifacts vs the fork point), and exit 1 only on `do not merge` or a
missing/illegal review. It no longer routes.

## Judge routing: a hook-posted fix task (the native idiom)

`fix-N` steps leave the plan. Instead, build-plan still authors and
readiness still validates the fix brief, but the task is *posted* only when
needed: a lifecycle hook script (their subscribable hook bus, `post_merge`,
`BERNSTEIN_TASK_ID` in the env) reads the judged phase's `verdict.json`
and, when `certain > 0`, POSTs the pre-briefed fix task to the task server.
Determinism is preserved - the brief was authored and pinned at plan time;
only the posting is conditional. This deletes `fix-noop` outright and
removes the "a verdict routes, it does not block" contortion from the gate.

## Skill-side changes (scripts and config, no package code)

- **build-run**: replace `bernstein-herdr run-config` with ~10 lines -
  write the 4-key `run_config.json`, pick a free port, freeze
  `refs/build/base/<slug>` via `git update-ref`, check `base_ref` matches
  the checked-out branch. Replace `watch` with a small SSE client script
  (`curl -N /events` + stall timer + exit on `run.completed`). Drop
  `triage`: the driver reads `status --json`, `runs report --json`, and
  `refused_merges.jsonl` directly. Resume becomes a script over the native
  run journal and per-task gate reports.
- **build-plan**: emit `files:` (-> `owned_files`), `completion_signals:`
  for witnesses, and `context_files:` for briefs on every step; fold the
  workflow-specific admission checks into `plan-check.py`, layered on
  native `bernstein plan validate` and `bernstein run --dry-run`.
- **bernstein.yaml template**: pin batching to one task per agent (a
  multi-task session has one `task_title`, which would misresolve the
  sidecar at merge time); keep `flaky_detection: false` (it appends pytest
  deselect args onto `command_override`); leave gate repair and janitor
  reopens at their defaults (ON) - adopted deliberately, since every
  repaired attempt is re-scored by our gate and judged at phase level.
- **Retired assumptions**: "exit 1 is TERMINAL" is deleted from every
  skill and docstring; the gate is documented as resume-idempotent.

## Deleted outright, with the native reason

`task_for_worktree`/`team.json`/`tasks.jsonl` forensics (plugin identity),
`fix-noop` (hook-posted fix task), `merged_ahead`/`short_circuit_sha`
complexity (shrinks into the memo), warm-pool/salvage refusals (#5344),
stale-pid sweep (native), `BERNSTEIN_SERVER_URL` plumbing (#5378),
file-tailing watch (SSE), `ledger.py` (run journal + gate reports +
review-board), `triage` (driver reads native JSON), `fake.py` (plugins are
pure functions; no adapter needed to test them).

## Open items to verify during build

1. Hook bus: confirm `post_merge` fires for judge-step merges and the hook
   env carries enough to locate the run dir; otherwise fall back to the
   driver posting the fix task between phases.
2. SSE `/events` auth: confirm the stream is reachable with the run's
   bearer token from a headless script.
3. Plugin pipeline declaration: explicit `pipeline:` entry
   `{name: scorer, required: true, condition: any_changed}` must coexist
   with the judge plugin gating judge-role steps only (plugin dispatch is
   per-pipeline, not per-role; the plugins no-op fast on non-matching
   steps via the sidecar).
4. Gate repair on judge steps: a judge blocked for editing code must NOT
   be "repaired" into a worktree that then edits more code - probe
   whether `[GATE-REPAIR]` respects role, and disable repair for judge
   steps if not (per-step config or a refusal marker in the gate output).

## Migration

Build `bernstein_operator/` alongside `bernstein_herdr/`, port the herdr
test scenarios that still apply (most hardening tests die with the code
they hardened), cut the skills over in one release, then delete
`bernstein_herdr/` in the same release. The uv install line changes only
in the `--with` path.

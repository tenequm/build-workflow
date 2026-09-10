---
name: build-run
description: "Execute a ready phase build unattended. Use /build-run <plan dir>, or alone in its workspace, for isolated native Bernstein runs, detached ACP judging between phases, receipt-bound fix mini-runs, and whole-tree validation."
---

# build-run

Input: a plan directory (or its plan.md), or the ACTIVE plan inside its linked
workspace. Output: a validated local branch and immutable attempt evidence under
`.agents/build/runs/<slug>/`. The driver never edits application code.

Resolve the sidecar whose `defaults.doc` names that plan.md. With no argument,
read `.agents/build/plans/ACTIVE`. Refuse missing or disagreeing matches. In a
primary checkout, enumerate linked workspaces with a workspace.json; re-enter
an unambiguous one, otherwise obtain the missing workspace identity. Never
improvise a plan or copy newer artifacts from the primary into a running build.

A run is unattended after the user's execution instruction. Existing authorization
persists; do not ask again. An unresolvable obligation parks with evidence and
ends the run. Do not widen scope, change a frozen brief or seed, or patch code
in the driver session. Record workflow defects in `<run>/ledger.md` as
`- workflow: <tag>: <what and why>`, where tag is instruction-wrong,
instruction-ambiguous, tooling-gap, engine-bug, driver-error or flaky.

Use absolute paths for actual commands. The examples use `<skill>` for this
skill's own installed directory and `<python>` for the interpreter in the
Bernstein uv tool environment (`uv tool dir` then `bernstein/bin/python`). No
script reads another skill's directory. Do not use an arbitrary system Python.

## Preflight

1. Require a linked workspace, attached integration branch, no superproject.
   Compare resolved git-dir and git-common-dir paths. Validate workspace.json's
   exact fields: path, branch, base, base_branch, primary; current root and branch
   must equal its path and branch.
2. Require the plan directory's report.md and no open Escalations. Require all
   authored inputs committed, the native scorer plugin installed, and all four
   engine compatibility patches present. The installed Python must import
   bernstein_operator and operator scripts from this skill. See the repository
   install instructions; do not mutate the engine or plugin during a live run.
3. Run this skill's checked hooks helper; its existing receipt preserves the
   original configuration captured by planning:

       <python> <skill>/scripts/workspace-hooks.py disable --root <workspace> --run <workspace>/<run>

4. Run the skill-local readiness checker from the workspace root:

       <python> <skill>/scripts/build-operator.py ready --root <workspace> --plan <machine.yaml>

   It checks frozen inputs, sign-off, roles, scopes, citations, disjointness,
   loaded completion signals, ingress isolation, patches, disk and commands in
   a detached baseline. Read every baseline validation result. Expected red
   witnesses must be explicitly explained in their brief; unexplained red is
   a planning defect. A command failure never becomes a baseline exemption.

## Execute and observe

Run the driver in an owned detached session with stdout/stderr recorded in
`<run>/driver.log`. Use subprocess.Popen with start_new_session=True and
record its PID plus creation time; do not use a shell background job that
shares the supervising agent's process group. The command is:

    <python> <skill>/scripts/build-operator.py run --root <workspace> --plan <machine.yaml>

The driver holds both its own flock and the native Bernstein PID marker,
including between runs. It freezes refs/build/base/<slug> once, journals every
launch and POST intent, and observes through an HTTP/journal poll loop. Never
launch `bernstein run`, `--from-plan`, a watcher or another scheduler alongside
it. Do not call `bernstein stop`: its soft-drain can merge rejected work.

Each phase launch uses a fresh run ID and port, an isolated authenticated task
server with a fresh tasks.jsonl, and full direct POSTs with completion_signals,
metadata, model policy and concrete phase-local dependency IDs. No explicit
IDs are reused. Only after verifying stored payloads does the driver start the
native orchestrator. Future-phase tasks do not exist yet. Native gate repair,
flaky deselection, test follow-ups, evolution and janitor reopens are off: a
step whose completion signal cannot be verified fails with its evidence rather
than re-running, because a reopened step that merges after an earlier attempt
already merged delivers that step twice. Semantic response
reuse is disabled by the mandatory source patch. Importable root TODO.md,
TASKS.md, .plan and native backlog contents block launch; new ingress during a
run parks it. Quarantined expected titles also park before execution.

The native engine owns worktrees, execution, janitor, retries, quality gates,
merge queues and reaping. A native DONE status may release a dependency before
merge, so a verified-before-start dependency must have been cut into another
phase. In-phase strict ordering is unsupported. Distinct phase roles avoid
batching; disjoint ownership avoids parallel edits to shared files.

Inspect without launching anything:

    <python> <skill>/scripts/build-operator.py status --root <workspace> --plan <machine.yaml>

The status output and workflow.jsonl are authoritative for driver obligations;
runs.jsonl and ledger.md are readable indexes. Native logs and per-run archived
reports explain failures. A native run_completed row or an empty task board is
not build completion. The driver requires run_quiescence, successful identified
scheduler exit, no residual children, stopped server and positive delivery for
every expected title: spawned task/attempt -> scorer PASS -> landed commit ->
integration ancestry. It archives native evidence and reconciles paired WAL
claims before any next run. Missing or contradictory evidence parks.

## Judge and fix ceremony

After a proven boundary, the driver stages the exact cumulative base..tip tree
in a detached worktree under `<run>/judge/<attempt>/worktree`. The pinned reviewer
runs through acpx in a fresh one-shot session. On the default `claude` transport,
budget, model and turn limits pass through ACP session metadata, user settings and
saved sessions are disabled, and the measured USD cost is required evidence; on
the `acp` transport any other ACP agent is asked for the same model, turn and
tool limits through acpx and reviews with no MCP servers, and an agent that
reports no cost leaves the ceremony unmeasured, so it settles at its whole
reservation. The judge receives the frozen brief, precise
range and tracked context. It writes only the three review artifacts. It never
commits or becomes an engine task. The driver checks tree/index integrity, reaps
children and rechecks the integration ref before archiving the receipt.

- Legal zero-certain verdict: accept this phase.
- Certain findings: POST the complete pinned fix as a separate native mini-run,
  embedding exact review bytes and hashes, then judge the new cumulative tip.
- Do not merge: park immediately.
- Malformed or missing output: one fresh ceremony, then park.
- Findings outside the pinned fix scope, integrity failures, refusal reports,
  uncertain launches or unaccounted tasks: park with evidence.

Ordinary fixes run the same scorer as every executor. No fix task exists for a
zero-certain verdict. No new brief or allowlist is invented mid-run. The final
phase must include whole-tree regression validation; its repairs use the same
whole-tree gate. Repeated repairs consume whole-build attempts, wall time and
spend reservations. Native reservations remain charged conservatively because
an observed native cost ledger is not a complete invoice.

## Recovery

After a driver interruption, use only:

    <python> <skill>/scripts/build-operator.py resume --root <workspace> --plan <machine.yaml>

Recovery reads the journal before acting, checks process identity and server
inventory, recovers server-generated IDs, and resumes the recorded obligation.
It never recreates an absent ambiguous POST or relaunches an uncertain process.
A persisted park remains parked; preserve its native logs, refused merges,
scorer receipts, judge attempts and graveyard refs for explicit resolution.
Do not reset tasks.jsonl, remove the WAL, use --fresh, reset the frozen base,
prune already merged steps into a new implicit run, or dispatch an ad hoc fix.
A new signed-off repair plan with a new slug is the supported scope change.

Evidence locations:

- workflow.jsonl: hash-chained intent/receipt/reaction authority.
- readiness/: frozen pins and admission receipt.
- native/<run-id>/: archived journal, tasks, runtime evidence and WAL.
- reports/<title-hash>/<attempt-id>/: scorer receipt, diff, report.
- judge/<attempt>/: exact review range, artifact hashes, process log and receipt.
- processes/: identified launches, completion receipts and logs.

Keep secrets out of pasted logs. The private workflow journal includes an
expired local server token; runs.jsonl omits it. Never edit immutable evidence.

## End local

Success requires build_completed and a current integration tip equal to its
receipt. Report measured outcomes and any owner:user obligations. Restore the
captured hooksPath with this skill's `scripts/workspace-hooks.py restore --root <workspace> --run <workspace>/<run>`. Keep the branch local. Open a PR only when authorized by
the user; if that decision is still missing, ask once after the validated result
is concrete. Do not automatically merge, publish, or delete the workspace.
Every authored commit uses Conventional Commits without attribution trailers.

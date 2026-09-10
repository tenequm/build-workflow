# build-workflow

Three self-contained skills for planning, running and landing a Bernstein build.
The driver plans and supervises; native Bernstein executors write application
code. Each phase gets its own engine run. Claude reviews the cumulative result
through ACP between runs, and actionable findings trigger a pinned fix mini-run.

## Install

Use the verified source revision and the four compatibility patches. A registry
installation cannot satisfy the current plugin-parser and semantic-cache checks.
These commands create an operator-owned source checkout; they do not alter an
existing upstream clone. Replace the example checkout paths with your own.

```sh
git clone https://github.com/tenequm/build-workflow.git "$HOME/pj/build-workflow"
git clone https://github.com/sipyourdrink-ltd/bernstein.git "$HOME/pj/bernstein-operator-engine"
git -C "$HOME/pj/bernstein-operator-engine" checkout --detach 0a6bf9f2d69daae4ad468a9ba6a2713f79d67fdf
python3 "$HOME/pj/build-workflow/skills/build-run/scripts/prepare-engine.py" "$HOME/pj/bernstein-operator-engine"
# --no-sources is required: the scorer package pins the engine by git revision
# for its own development lock, which conflicts with this patched local checkout.
uv tool install "$HOME/pj/bernstein-operator-engine" \
  --with "$HOME/pj/build-workflow/bernstein_operator" --python 3.13 --force --reinstall --no-sources
npm install -g acpx@0.15.1
# Fetch the pinned adapter before an unattended run. Its Claude authentication
# must already work; this help command does not make a model call.
npx --yes @agentclientprotocol/claude-agent-acp@0.60.0 --help
npx -y skills add tenequm/build-workflow -y \
  --skill build-plan --skill build-run --skill build-close
```

The native Codex adapter passes only `-m`, so Codex effort comes from
`~/.codex/config.toml`. Readiness requires every codex role's declared `effort`
to equal that file's `model_reasoning_effort`, where an absent key means
`default` (the model's own): set the key to `"high"` for a production build and
declare `high`, without duplicating the key. Install/authenticate the Claude and
Codex CLIs.
Find the execution interpreter using `uv tool dir`: use the resulting
`<tool-dir>/bernstein/bin/python` for skill scripts. The scorer and engine must
share that environment. Do not use the package's development environment for
a paid build: its locked upstream source is patched only in the test harness.

`prepare-engine.py` applies only four exact changes and fails on unfamiliar
source: seed validation consults the installed gate registry; the orchestrator
honors `BERNSTEIN_RESPONSE_CACHE=0`; merge-back skips fetch, rebase and push when
`BERNSTEIN_OPERATOR_LOCAL_ONLY=1`; and the orchestrator's quiescence self-stop
counts a merged task, which the store archives as `closed` - without it a run
whose every task merged never stops and never journals the phase boundary this
workflow waits for. Rebuild after patching. Readiness checks the
installed code and exercises the real parser. Upstream replacements require a
new verified source pin and acceptance run, not removal of admission checks.

## Workflow

1. `/build-plan`: signed-off spec, derived plan, witnesses where needed, explicit
   phases, tracked executor/fix/judge briefs, an isolated workspace and readiness.
2. `/build-run <plan dir>`: one authenticated server and native run per phase,
   positive delivery reconciliation, detached Claude ACP judging, bounded fixes,
   and a final whole-tree regression phase. Ends with a local validated branch.
3. `/build-close <plan dir>`: authorized merge/release, outcome report, verified
   evidence preservation, then workspace cleanup.

Each skill carries its own scripts and templates. A skill never reads another
skill's installed directory. The repository's sync check verifies shared copies.
Starting execution authorizes its planned paid work. Publishing and merging use
existing user authorization or an explicit final decision.

## What runs where

| Component | Location | Responsibility |
|---|---|---|
| Skill driver scripts | isolated integration workspace | admission, phase launch/poll, receipts, recovery |
| Native Bernstein server/orchestrator | one fresh ID and port per phase or fix | task scheduling, retries, worktrees, janitor, gate calls, merging, reaping |
| Native resolver/ci-fixer executors | agent worktrees | Codex gpt-5.6-sol, high effort |
| Native analyst executors | agent worktrees | Claude claude-opus-5, high effort |
| Claude ACP judge | detached workflow-owned worktree | fresh blind cumulative review with model/turn/time/spend limits |
| Installed scorer plugin | executor worktree at both native gate call sites | observed diff, ownership, validation, report checks and immutable receipts |

The Python package installs only the scorer entry point. Coordination lives in
`skills/build-run/scripts/`, admission copies in build-plan, and preservation in
build-close. No judge task, judge gate, post-merge hook or no-op fix exists.
Native DONE releases dependencies before merge: verified-before-start edges must
cross phase boundaries. Per-phase roles are distinct to prevent batching.

## Commands

Run from the workspace using the installed Bernstein interpreter:

```text
<python> <build-plan-skill>/scripts/plan-check.py <plan-dir> --repo <workspace> --machine <plan.yaml>
<python> <build-run-skill>/scripts/build-operator.py ready --root <workspace> --plan <plan.yaml>
<python> <build-run-skill>/scripts/build-operator.py run --root <workspace> --plan <plan.yaml>
<python> <build-run-skill>/scripts/build-operator.py resume --root <workspace> --plan <plan.yaml>
<python> <build-run-skill>/scripts/build-operator.py status --root <workspace> --plan <plan.yaml>
<python> <build-close-skill>/scripts/preserve-evidence.py --root <workspace> --run <run-dir> --dest <primary-run-dir>
```

The driver starts the server alone, POSTs full task payloads, verifies admission,
then starts the orchestrator directly. Never run normal bootstrap or soft-drain
alongside it. Native process closure alone is insufficient: every expected step
needs a scorer PASS for its delivered content and ancestry in the reviewed tip.
A missing link, unexpected task, refusal or integrity error parks the build.
Resume reconciles durable intent against the existing server and process state;
ambiguous absent effects park rather than creating duplicates. A parked scope
change requires a newly authored build with a new slug.

## Artifacts and limits

```text
<plan-dir>/spec.md, plan.md, facts.md, report.md    tracked human/machine plan layers
.agents/build/plans/<slug>.yaml                   complete authored task inventory
.agents/build/plans/<slug>.steps.yaml             phases, bounds, judge config, scorer policy
.agents/build/plans/<slug>/                       tracked briefs
.agents/build/runs/<slug>/workflow.jsonl           private durable intent/receipt journal
.agents/build/runs/<slug>/readiness/              frozen admission evidence
.agents/build/runs/<slug>/native/<run-id>/         native evidence archived before retention
.agents/build/runs/<slug>/reports/<title>/<id>/    scorer attempts
.agents/build/runs/<slug>/judge/<attempt>/         immutable review range and evidence
.agents/build/runs/<slug>/processes/               launches, logs and exit receipts
```

The driver freezes `refs/build/base/<slug>` once and records each phase start tip.
Judges review cumulatively from that base. Fix inputs embed exact review bytes;
findings outside a pinned fix allowlist park. One malformed review is retried;
`do not merge` parks immediately. Whole-build limits count every native run and
judge attempt, include downtime, and retain native spend reservations even when
reported costs are low. Provider calls already in flight can exceed a requested
budget at the turn boundary; the driver checks the final measured cost.

Reserve at least 40 GiB free disk, cache required dependencies, and disable shared
Git hooks before admission. Root TODO.md, TASKS.md, .plan and native backlogs must
be absent/empty; quarantined expected titles cannot launch. A final single
regression executor tests the combined tree. Native retention keeps only a finite
run history, so build-close verifies the workflow archive and creates a portable
Git bundle before deleting anything.

## Development

```sh
cd bernstein_operator
just install    # Python 3.13, uv.lock, Ruff, ty, pytest
just check      # types, lint, format and vendored skill-code consistency
just test -q    # installed scorer + isolated patched native source; no paid agents
just fix
```

The existing Lefthook setup runs the local checks. CI is intentionally omitted.
After meaningful skill/template changes use root `just ship`, which bumps both
plugin manifests together, commits and pushes. Internal/doc-only changes may push
without shipping. `bernstein_herdr/` remains in the repository after the operator
cutover; retaining it is intentional. The new skills use `bernstein_operator`.

Historical replays need a separate clone without the answer in its object store.
Normal forward builds use linked worktrees and keep the primary checkout free.

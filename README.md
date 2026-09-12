# build-workflow

Three self-contained skills for planning, running and landing a Bernstein build,
and a fourth for reviewing someone else's pull request. The driver plans and
supervises; native Bernstein executors write application code. Each phase gets its
own engine run. A detached ACP reviewer judges the cumulative result between runs,
and actionable findings trigger a pinned fix mini-run.

`/review-pr` is the review half, and it owns no orchestrator of its own: it hands
one free-text review goal and a model seed to a stock `bernstein run` inside a
checkout of the target repository. Bernstein spawns the agents, routes the models
and holds the budget; the skill supplies only the doctrine the review follows and
reads back the report. Public repositories only, and nothing is ever posted.

## Install

Use the verified source revision and the four compatibility patches. A registry
installation cannot satisfy the current plugin-parser and semantic-cache checks.
These commands create an operator-owned source checkout; they do not alter an
existing upstream clone. Replace the example checkout paths with your own.

```sh
git clone https://github.com/tenequm/build-workflow.git "$HOME/pj/build-workflow"
git clone https://github.com/sipyourdrink-ltd/bernstein.git "$HOME/pj/bernstein-operator-engine"
git -C "$HOME/pj/bernstein-operator-engine" checkout --detach ebad8f5b3612c117a6909684f4913962362fae63
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
  --skill build-plan --skill build-run --skill build-close --skill review-pr
```

`/review-pr` needs a `bernstein` on PATH, `gh`, `git`, and, for the local-first
lane, a `pi` CLI configured against a local LiteLLM gateway in
`~/.pi/agent/models.json`, serving `qwen3.8-flash-next`, `qwen3.8-27b-nvfp4` and
`qwen3.6-35b-a3b-nvfp4` (the seed writes the ids as `litellm/<id>`). That lane costs
nothing, has no rate limits and keeps prompts on the machine. The alternative mix is the subscription lane: an
authenticated `claude` CLI for the manager and `agy` for the worker roles. Either
way the skill needs no patched engine checkout, no scorer plugin and no readiness
command; it ships no Python at all, and it stays fenced to public repositories and
this repository's own eval corpus, with no GitHub token in reach of a model session.

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

The pinned commit is upstream main of 2026-09-11; all six prerequisite patches
were verified to apply to it that day, and the engine actually installed on a
machine may be an older snapshot until it is rebuilt from this pin.

`prepare-engine.py` applies only six exact changes and fails on unfamiliar
source: seed validation consults the installed gate registry; the orchestrator
honors `BERNSTEIN_RESPONSE_CACHE=0`; merge-back skips fetch, rebase and push when
`BERNSTEIN_OPERATOR_LOCAL_ONLY=1`; the orchestrator's quiescence self-stop
counts a merged task, which the store archives as `closed` - without it a run
whose every task merged never stops and never journals the phase boundary this
workflow waits for; a quarantined task is failed rather than skipped while still
`open`, which otherwise leaves the raw open count above zero and wedges the run
forever; and the host-local Agency persona cache loads only when the seed's
`catalogs:` registry actually enables it, so a role's system prompt stops
depending on what happens to sit under `$HOME`. Rebuild after patching. Readiness checks the
installed code and exercises the real parser. Upstream replacements require a
new verified source pin and acceptance run, not removal of admission checks.

## Workflow

1. `/build-plan`: signed-off spec, derived plan, witnesses where needed, explicit
   phases, tracked executor/fix/judge briefs, an isolated workspace and readiness.
2. `/build-run <plan dir>`: one authenticated server and native run per phase,
   positive delivery reconciliation, detached ACP judging, bounded fixes,
   and a final whole-tree regression phase. Ends with a local validated branch.
3. `/build-close <plan dir>`: authorized merge/release, outcome report, verified
   evidence preservation, then workspace cleanup.

Separately, `/review-pr <number>` reviews a public pull request: fetch the diff and
the pull request body into the checkout, then one `bernstein run` carrying the
skill's review goal and seed. The doctrine the goal carries - read authority files
whole on the base branch, take any validation command from the base branch, name the
input that breaks a defect - is what the reviewing agents follow. The run writes
`review-report.md` at the checkout root; you read it and decide.

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
| ACP judge | detached workflow-owned worktree | fresh blind cumulative review with model/turn/time/spend limits; `claude` binds them through its session bridge, `acp` asks acpx for them |
| Installed scorer plugin | executor worktree at both native gate call sites | observed diff, ownership, validation, report checks and immutable receipts |
| Review run (`/review-pr`) | a stock `bernstein run` in a checkout of the reviewed repository | bernstein owns spawning, worktrees, model routing and the budget; the skill owns only the goal text and the seed |

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

`/review-pr` is separate, ships no scripts, and runs from a checkout of the
reviewed repository with its BASE commit checked out:

```text
gh pr diff <n> > .bernstein-pr.diff
gh pr view <n> --json title,body --template '# {{.title}}

{{.body}}' > .bernstein-pr.md
bernstein run --seed <review-pr-skill>/templates/review-seed.yaml \
  --goal "$(cat <review-pr-skill>/templates/review-goal.md)" \
  --budget '$3.00' --auto-approve --quiet --wait 3000
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

`just test` proves the driver's contracts against recorded agents. What no
recording reaches - dispatch, real merges, quiescence timing, judge transports
and whether a model can follow a brief - is proven by a fixture:

```sh
python3 fixtures/slugify/setup.py /tmp/fx   # a ready workspace, then its printed commands
```

It builds one step with one judge in minutes against real providers. Run it
when a change touches the phase boundary, the scorer, the judge ceremony or a
template a plan author copies; see [fixtures/README.md](fixtures/README.md).

The existing Lefthook setup runs the local checks. CI is intentionally omitted.
After meaningful skill/template changes use root `just ship`, which bumps both
plugin manifests together, commits and pushes. Internal/doc-only changes may push
without shipping. `bernstein_herdr/` remains in the repository after the operator
cutover; retaining it is intentional. The new skills use `bernstein_operator`.

Historical replays need a separate clone without the answer in its object store.
Normal forward builds use linked worktrees and keep the primary checkout free.

# Research overview, 2026-09-02

Everything discovered and considered in the session that produced this repo.
Sources are linked; numbers are the ones measured or quoted, with their tier
(measured by us, lab-reported, paper, second-hand). Companion decision record:
`docs/2609-02-design.md`. Raw eval records live in the `personal` repo under
`docs/codex-subagents-herd-eval/` (runs.jsonl, per-run dirs, judge ledgers).

## 1. Executor evals (measured by us)

Two corpora, replayed from identical base commits with identical briefs, one
detached worktree per run, capture on settle, blind judges afterwards.

- nanoclaw (TypeScript fork, polish fixes, 2026-08-31 Codex originals): cases
  A exact lines, B transfer with acceptance criteria, C decided designs on hot
  paths, D symptoms only. Replayed: B, D (D x3).
- gopost v3 (Go, seam-heavy rewrite, 2026-09-01): phases 0b, 1a, 1b, 2, 3, 4,
  5a, 5b, 6, 7, 8 and fix briefs. Replayed: 1a, 1b, 2, 5a, 5b.

Arms: Codex 0.151/0.152 gpt-5.6-sol high (`--approve-for-me --no-alt-screen`);
Claude Code 2.1.252 Opus 5, 4.8, 4.6 (`--permission-mode auto`; the driving
session's classifier refuses `--dangerously-skip-permissions`); Antigravity CLI
1.1.24 Gemini 3.7 Flash high via herdr kind `agy` (2026-09-02, seven runs
concurrent). Judges: one fresh Fable 5 subagent per case per round, labels
shuffled, measuring gates itself on a clean lint cache, revert-checking tests,
probing defects with throwaway tests.

### Round 1 (2026-09-01, 7 cases)

| case | shape | judge ranking | certain defects codex / opus5 / other | wall codex / opus5 |
|---|---|---|---|---|
| gopost 1a | additive platform layer | Opus 5 > Codex | 6 / 0 | 15m+6m fix / 15.6m |
| gopost 1b | contract + harness + registry | Codex > Opus 5 | 1 / 1 | 24m / 23m |
| gopost 2 | schema reset + queries | Opus 5 > Codex > 4.8 > 4.6* | 3 / 0 / 5, 7* | 25m / 19.5m |
| gopost 5a | engine loops + meter | Opus 5 > Codex | 4 / 0 | 29m / 34m |
| gopost 5b | engine facts + publish | Opus 5 > Codex | 4 / 0 | 23m / 23m |
| nanoclaw B | transfer | Codex > Opus 5 | 0 / 1 | 17m / 8.7m |
| nanoclaw D | symptoms only | Opus 5 x2 > Codex > 4.8 | 0 / 0 / 0 | 15.5m / 15m |

*4.6 confounded: thinking effectively off (20 thinking tokens over 149 calls),
two mid-run compactions.

Totals: Opus 5 first in 5 of 7; certain defects Codex 18, Opus 5 2. Cost per
phase from transcripts (pond, dedup rules of the 2026-08-27 accounting note):
Opus 5 $7.90-27.19; Codex $1.64-4.38 at GPT-5 list as proxy, 97.8% cache hits.

### Round 2 (2026-09-02, 6 cases, Flash added, labels reshuffled)

| case | ranking | certain defects (Flash / Opus 5 / Codex) | Flash verdict |
|---|---|---|---|
| 1a | Opus 5 > Flash > Codex | 3 / 1 / 5 | merge after fixes |
| 1b | Codex > Opus 5 > Flash | 7 (lint red, 17 issues) / 2 / 1 | do not merge |
| 2 | Opus 5 > Codex > Flash > 4.8 > 4.6 | 2 / 0 / 3 | merge after fixes |
| 5b | Opus 5 > Flash > Codex | 0 / 0 / 2 | two items missing |
| B | Opus 5 > Flash > Codex | 0 (1 cosmetic) / 0 / 0 | merge after fixes |
| D | Codex > Opus 5 x2 > 4.8 > Flash | 1 + two inert tests / 0 / 1 | do not merge |

Flash: never first; 13 certain defects; wall 8-16 min, about 0.55x Codex, with
all seven runs sharing one CPU. 5a was not judged: the Google AI Pro individual
quota closed after 478 steps ("Resets in 4h34m"); the seven sessions had
consumed 6.7M fresh + 155M cached input and 0.7M output tokens in 25 minutes,
about $19 at list ($0.75/M fresh, $0.075/M cached, $3.75/M output; introductory
to 2026-12-31, doubling after).

Two Flash failures verified in its session DB, not by a judge: on 1b it ran
lint on the whole module, hit the expected-red packages, never ran the brief's
scoped lint, and wrote a report with no lint section and "Deviations: None"; on
D its D2 test passed on the unmodified base.

Judge variance: rankings flipped between rounds on B and D. Reproduced-defect
counts are steadier than ranks. All judges were Fable; no cross-family judge
has run (a same-family lean toward Opus is possible in ranks).

### Antigravity CLI specifics

- Sessions are protobuf-in-SQLite at `~/.gemini/antigravity-cli/conversations/<id>.db`,
  not indexed by pond. `protoc --decode_raw` on `steps.metadata` gives per-step
  timestamps and a usage record on step type 15 (fields: 1 constant, 2 fresh
  input, 3 output, 5 cached input, 9 thinking, 10 text output); step type 132 is
  a tool call. Decoder: `bernstein_herdr/agy_session.py`.
- herdr 0.8.2 has an official antigravity-cli integration; open bugs: the trust
  prompt reads as idle ([herdr#3419](https://github.com/herdrdev/herdr/issues/3419)),
  subagent generation reads as idle ([#2354](https://github.com/herdrdev/herdr/issues/2354)).
  Pre-trust worktree paths in `~/.gemini/antigravity-cli/settings.json`;
  `toolPermission: always-proceed` is the unattended mode.
- Launch: `herdr agent start <name> --kind agy -- --model gemini-3.7-flash-high`.
  glim MCP OAuth failed (dynamic client registration 429); never used by any arm.

### Process findings that generalise

- The driver's own review missed 18 certain defects across five merged Codex
  diffs; a blind judge found them all. Judge before merge.
- Codex over-claimed lint twice on a warm golangci cache; every gate cleans the
  cache first.
- Every executor honoured allowlists and reported walls instead of hacking
  around them; that is why seams stayed clean where code did not.
- `herdr agent wait` settles on transient idle for every kind; the report file
  on disk is the settle signal.
- `.agents/` is gitignored and dies with a worktree; recover briefs and
  reports before removal.
- Orchestrators that implement and then patch their own code at 400-590k
  context created about 45% of what the next review round found (2026-08-26/27
  forensics). Fixes go to a fresh executor with a brief.

## 2. Where the wall went (gopost v3, 2026-09-01, pond)

| block | wall | executor minutes |
|---|---|---|
| design pass, one Fable session | 11:35Z-15:25Z, 3h50 | 0 |
| build 0b..10 plus fix briefs | 15:33Z-19:06Z, 3h33 | 373 across 21 Codex sessions, 1.8x parallel |
| polish A-D, hotfixes, reconnect, notif, rsub, dueurl | 19:56Z-23:43Z, 3h47 | 335 across 11 sessions |

Critical chain 0b, 1a, 1b, 3/4/7, 5a, 5b, 6, 6fix, 10: about 210 executor
minutes of 213 wall. Driver gaps 2-15 min. The driver session had 193 user
turns. Executor speed moves only the middle block; Flash saves about 90 min
there and gives most back in fix rounds. Opus 5 costs no chain time and cuts
the tail.

## 3. Angles (evidence in sections 4-6)

1. DAG dispatch off the driver's attention.
2. Speculate past the judge behind a commit barrier.
3. Multiple candidates, execution-filtered, cross-family, disagreement-driven.
4. Plan for decomposability; critique the plan before launch.
5. Verification as a ratchet with evidence; judge never weaker than executor.
6. The tail as a background stream.

## 4. Lab guidance (lab-reported unless noted)

Anthropic
- [Building a C compiler with a team of parallel Claudes](https://anthropic.com/engineering/building-c-compiler): 16 agents, ~2,000 sessions, $20k, no orchestrator; lock files + git push rejection; specialised agents.
- [Long-running Claude for scientific computing](https://anthropic.com/research/long-running-Claude): one sequential agent with subagents for coupled pipelines; CLAUDE.md as plan, CHANGELOG as memory, reference implementation as oracle.
- [Code Review](https://claude.com/blog/code-review): substantive comments 16% -> 54% of PRs; parallel bug-class agents then a verification step; ~20 min, $15-25.
- [Using LLMs to secure source code](https://claude.com/blog/using-llms-to-secure-source-code): adversarial verifier halved non-exploitable findings; requiring a PoC drove false positives to near zero.
- [A harness for every task](https://claude.com/blog/a-harness-for-every-task-dynamic-workflows-in-claude-code): names tournament, generate-and-filter, adversarial verification; pairwise beats absolute scoring; self-preferential bias; "most coding tasks do not need five reviewers".
- [Dynamic workflows](https://claude.com/blog/introducing-dynamic-workflows-in-claude-code): Bun's Zig-to-Rust port, two reviewers per file, 11 days.
- [Multi-agent research system](https://anthropic.com/engineering/multi-agent-research-system): 90.2% over single agent, 15x tokens; coding has fewer parallelisable tasks than research.
- Docs: agent teams (no worktree isolation, partition files by owner), `claude --worktree` enforcement, dynamic workflows caps (16 concurrent), `subagentPromptCacheTtl`.

OpenAI
- [Harness engineering](https://openai.com/index/harness-engineering): 1M LOC, 3 engineers, 3.5 PRs/engineer/day; AGENTS.md as table of contents; linters that inject remediation; minimal blocking gates.
- [Symphony](https://openai.com/index/open-source-codex-orchestration-symphony): humans cap at 3-5 interactive sessions; ticket DAG with auto-restart gave +500% landed PRs; objectives, not state transitions.
- [Scaling code verification](https://alignment.openai.com/scaling-code-verification): reviewer tuned for precision; 46% of its comments on Codex PRs cause a change; verification far cheaper than generation.
- Codex docs: subagents, `codex cloud exec --attempts`, effort protocol (baseline, one lower, raise on evals only).

Google
- Antigravity: subagents with `branch` workspace mode; Teamwork roles Critic, Challenger, Auditor, Success Auditor and integrity modes; closed source; leaked orchestrator prompts show a `.agents/` tree with `ORIGINAL_REQUEST.md`, `PROJECT.md`, per-agent `plan.md`/`progress.md`/`BRIEFING.md`.
- [Jules planning critic](https://jules.google/docs/changelog/2026-01-26-1): 9.5% fewer task failures.
- Thinking levels: MEDIUM default for agentic coding; below MEDIUM causes premature tool termination.
- [Gemini 3.7 Flash](https://blog.google/innovation-and-ai/models-and-research/gemini-models/introducing-gemini-3-7-flash): DeepSWE 65.3% vs 49.0% for 3.6.

## 5. Literature (papers unless noted)

Best-of-N and verifiers
- [Large Language Monkeys](https://arxiv.org/abs/2407.21787): coverage 15.9% -> 56% at N=250 on SWE-bench Lite; no verifier saturates.
- [Inference Scaling fLaws](https://arxiv.org/abs/2411.17501): verifier false-positive rate is a hard ceiling; optimal N under 10.
- [SWE-Gym](https://arxiv.org/abs/2412.21139), [R2E-Gym](https://arxiv.org/abs/2504.07164), [Agentic Rubrics](https://arxiv.org/abs/2601.04171), [CodeMonkeys](https://arxiv.org/abs/2501.14723): verifier-selected captures about half the headroom; hybrids +7-8 pts; the rubric author matters more than the judge model.
- [Scaling TTC for agentic coding](https://arxiv.org/abs/2604.16529): 16 rollouts + tournament voting, +4.4-8.4 SWE-bench Verified, +7.3-16.2 Terminal-Bench.
- [AI21 budget-aware best-of-N](https://ai21.com/blog/improving-best-of-n-with-budget-aware-execution-for-swe-agents): parallel with early kill -25% latency.

N-version and diffing
- [N-Version Programming with Coding Agents](https://arxiv.org/abs/2606.20158): 429 coincident failures where independence predicts 115; agents converge on the same wrong formula across families.
- [Failure Independence in LLM-Generated Code](https://arxiv.org/abs/2607.02808): cross-family ensembles realise 43-44% of the theoretical gain, same-model under 30%.
- [DiffTrust](https://github.com/mpi-softsec/difftrust): disagreement detects ~2/3 of incorrect programs at zero false positives.
- [Are "Solved Issues" Really Solved?](https://arxiv.org/abs/2503.15223): 29.6% of plausible patches diverge behaviourally.

LLM-as-judge for code
- [LLM-as-a-Judge for Code](https://arxiv.org/abs/2507.16587): kappa 0.10-0.21 vs execution truth; accepts half of incorrect Java.
- [Don't Judge Code by Its Cover](https://arxiv.org/abs/2505.16222): a "correct code" comment swings verdicts 20+ pts.
- [Google human-in-the-loop patch eval](https://arxiv.org/abs/2511.10865): with a per-bug rubric kappa 0.75.
- [Self-preference](https://arxiv.org/abs/2604.06996): judges >50% likelier to pass a criterion their own model failed.
- [Review direction](https://arxiv.org/abs/2607.21656) via [LeadDev](https://leaddev.com/ai/your-ai-coding-agents-might-need-an-org-chart): Claude reviewing Codex 71.6 -> 89.7; Codex reviewing Claude 91.4 -> 82.8; cost x2.3, latency x2.9.
- Generated tests need a gold gate ([2606.16062](https://arxiv.org/abs/2606.16062), single author): 61.9% of decisive generated tests fail on the gold patch.

Speculation
- [Speculative Actions](https://arxiv.org/abs/2510.04371), [Cost-Aware Speculative Execution](https://arxiv.org/abs/2606.07846), [Sherlock](https://arxiv.org/pdf/2511.00330), [Atomix](https://arxiv.org/pdf/2602.14849): start downstream before upstream verifies only for side-effect-free, idempotent or stageable work with rollback; 37-57% success vs 0-7% without.

Decomposition and multi-agent
- [Capable models outgrow collaboration](https://nature.com/articles/s42256-026-01268-y): decomposability decides; +80.8% on independent subtasks, -70% on sequential; SWE-bench-class work sits where extra agents add nothing at matched compute.
- [MAST](https://arxiv.org/abs/2503.13657): 41.8% of multi-agent failures are specification, 36.9% inter-agent misalignment, 21.3% verification.
- [When Parallelism Pays Off](https://arxiv.org/abs/2606.00953): dependency-graph partition 1.81x at -28% cost; naive file split 1.56x at +60%.
- [What Makes a Good Bug Report for an AI Agent?](https://arxiv.org/abs/2607.07593): +1 SD length = 51% lower odds; headers alone 30.4 pp.
- [Ask or Assume](https://arxiv.org/abs/2603.26233): an underspecification detector 54.8% -> 69.4%.
- [AgenticFlict](https://arxiv.org/abs/2604.03551): 27.67% merge-conflict rate for AI-authored PRs.
- Cognition (first-party): writes stay single-threaded; extra agents review and consult.

Throughput measurement
- METR: the 2025 19% slowdown is superseded by the [Feb 2026 update](https://metr.org/blog/2026-02-24-uplift-update) with CIs crossing zero; the design was abandoned partly because concurrent agents made time-on-task unmeasurable.
- [SWE-Effi](https://arxiv.org/abs/2509.09853): failed runs cost ~4x successes.

## 6. AVO and avo-lite

[AVO paper](https://arxiv.org/html/2603.24517v1) (NVIDIA): the agent is the
variation operator; 7 days, 500 directions, 40 committed versions, +3.5% over
cuDNN, +10.5% over FA4. Transferable: scorer with a hard correctness gate
separate from the objective, committed lineage the agent can read, retrievable
knowledge base, commit ratchet, mechanical stagnation detection with a rare
supervisor redirect. Precondition: a fast, automated, near-deterministic scorer.
[avo-lite](https://github.com/Git-on-my-level/avo-lite): one dependency-free
Python file; disposable worktree per tick; scorer, verifier and supervisor as
plain executables; append-only ledger; pins; rank and discover modes.
Adopted as invariants, not as a second scheduler.

## 7. Orchestrator survey (verified from READMEs and docs; stars as of 2026-09-02)

| tool | stars | verdict |
|---|---|---|
| [Bernstein](https://github.com/sipyourdrink-ltd/bernstein) | 1.1k, beta, solo | adopted: deterministic scheduler, YAML plans, worktrees, gates, adapters and gates as entry points |
| [Gas Town](https://github.com/gastownhall/gastown) | 17.9k | full loop incl. bisecting merge queue and watchdogs; owns tmux, Dolt, ~/gt; collides with herdr |
| [Agent Orchestrator](https://github.com/Untrivial-ai/agent-orchestrator) | 10.8k | LLM orchestrator, desktop app + daemon, 26 harnesses incl. agy |
| [oh-my-symphony](https://github.com/cskwork/oh-my-symphony) | 24 | codex/claude/gemini/agy/pi as peer backends, blocked-by graph, SQLite leases; merge is manual |
| [Microsoft Conductor](https://github.com/microsoft/conductor) | 414 | YAML workflows, no LLM in routing; SDK providers, no Codex CLI or agy |
| [pi-workflows](https://github.com/osolmaz/pi-workflows) | 255 | best engine design; agent nodes are Pi conversations; patterns copied |
| [Stoneforge](https://github.com/stoneforge-ai/stoneforge) | 177, last push May | Director/Workers/Stewards, event-sourced; claude/codex/opencode only |
| [OpenAI Symphony](https://github.com/openai/symphony) | 27k | Elixir spec bound to the Codex app-server; read for ticket DAG and stall rules |
| Claude Squad, Worktrunk, Superset, Orcha, Emdash, Baton, Contrabass, Maestro, Backlog.md, Vibe Kanban (sunset) | | worktree substrate or partial; not orchestrators for our shape |
| Antigravity Teamwork | closed | role vocabulary (Critic, Challenger, Auditor, Success Auditor) and the `.agents/` artefact tree are the reusable parts |
| [acpx](https://github.com/openclaw/acpx) | 3.2k | ACP transport: typed `end_turn`, usage per turn, protocol permissions, `compare`, flows (parent of pi-workflows); no agy; not adopted to avoid a second transport |
| Claude Code dynamic workflows | | not adopted: harness lock |

Roundups consulted: [Augment's open-source orchestrators](https://www.augmentcode.com/tools/open-source-agent-orchestrators), [awesome-herdr](https://github.com/yigitkonur/awesome-herdr), Reddit r/ClaudeAI and r/ClaudeCode threads on parallel sessions, Hacker News Show HN posts (Stoneforge, Parallel Code, Wtx, Harness, Scape, Hyve, Emdash, Agent Orchestrator, Orcha, Optio, Superset).

## 8. herdr ecosystem sweep (topics herdr-plugin and herdr, ~1,600 repos)

Sixteen references; two lessons every serious one converged on: completion is
a report or verdict file, never the agent status; the judge writes a closed
verdict set to a file cleared before the next round, in its own worktree
pinned to the dispatch SHA, and infra failure is never a block.

| we build | copy from |
|---|---|
| herdr adapter | [herdr-board](https://github.com/nelsonPires5/herdr-board) `docs/herdr.md` launch order; [paddock](https://github.com/lntvan166/paddock) `src/server/herdr/actions.ts`, `docs/gotchas.md`; [herdkit](https://github.com/briankeegan1/herdkit) `.driver` seam |
| scripted gates | herdkit `templates/healthcheck.node.sh` (0 clean / 1 code / 2 env); [crabbox](https://github.com/openclaw/crabbox) `--require-artifact`; [herdr-orchestrator](https://github.com/sean1588/herdr-orchestrator) `github_commits{since: state_entry}` |
| blind judge | [herdr-adversarial-review](https://github.com/overflowy/herdr-adversarial-review) `reviewer.sh`; herdr-orchestrator `decision.go`; [herdr-loop-lab](https://github.com/firegnu/herdr-loop-lab) cross-model judge reading only `git diff BASE...HEAD` |
| speculative merge | nothing direct; [herdr-conductor](https://github.com/StructuPath/herdr-conductor) preview, receipt, CAS-or-void |
| best-of-N | [herdr-swarm](https://github.com/StructuPath/herdr-swarm) fan-out and CAS harvest; scripted selection exists nowhere |
| ledger and lanes | [herdr-dagr](https://github.com/aemrebarut/herdr-dagr) `CONTRACT.md` evidence tiers verified/reported/heuristic/asserted; herdkit `outcome-ledger.sh`; [shepherd](https://github.com/ryonakae/shepherd) `schema.ts` |

The canonical socket API spec: herdr repo
`docs/next/website/src/content/docs/socket-api.mdx`; `herdr api schema --json`.

## 9. Patterns copied from pi-workflows and acpx

Effects declare recovery before running (idempotent vs manual; ambiguous parks);
claims with generations; content-addressed sources, resume refuses change; step
contract with attempt ids validated on submit; protected human decisions that a
model tool cannot answer; compose by named exits; progress never routes;
one status projection; judge children with read-only tools and a verified model.
Read in source: `controllers/effects.ts` (130 lines) matches the doc.

## 10. Bernstein code findings (clone at ~/pjv/sipyourdrink-ltd/bernstein, head 8396e7e84)

- Adapters load from the `bernstein.adapters` entry-point group
  (`adapters/registry.py:207-229`); the `generic` adapter is hardcoded to a
  `generic-cli` binary. `CLIAdapter.spawn()` returns `SpawnResult(pid, log_path, proc)`.
- Executors commit on `agent/<session_id>`; the merge diffs `HEAD...branch`
  into whatever branch the repo root has checked out, refusing the default
  branch (`spawner_merge.py:557`); blast-radius, signed file scope and quality
  gate refusals sit on that path. One repo root = one live integration branch.
- Completion contract `worker-completion/v1`: summary, files changed,
  verification command and exit code, or a typed refusal (`scope_exceeded`,
  `underspecified`, `awaiting_operator`, `blocked_on_dependency`).
- `GatePlugin.run(changed_files, run_dir, task_title, task_description) -> GateResult`;
  plugins from `.bernstein/gates/*.py` or the `bernstein.gates` entry point.
- Gate failure feeds `record_and_escalate()` in the cascade router.
- Plan schema is strict (`additionalProperties: false`), hence the sidecar.
- Merge queue is FIFO with `git merge-tree` conflict detection.
- agy adapter verified against 1.0.0, uses `-p --sandbox --dangerously-skip-permissions`.
- Sizes: adapters/base.py 1,498; janitor.py 2,367; gate_runner.py 1,960; spawner_merge.py 1,217; 2,014 Python files.

## 11. Decisions and cuts

Adopted: Bernstein engine; herdr adapter only (no acpx); Opus 5 on seam and
investigation steps, Codex on transfer, exact-line and fix steps; Flash as a
per-step shadow lane archived for later judging; judge as a plan step after
merge with dependents started (speculation); `fix-N` and optional `polish-N`
nodes; scripted scorer with report-accuracy check; readiness gate with source
pins; `docs/spec.md` at the root, section numbers frozen, "DESIGN n" label
kept; run directories under `.agents/build/runs/<slug>/`, plans tracked under
`.agents/build/plans/`; skills take the run dir as an argument.

Cut from v1: acpx, tournaments and automated selection, the AVO kernel,
controllers, discard-and-relaunch speculation, cross-model auto-selection,
agent teams, Claude Code dynamic workflows.

## 12. Not verified

Whether `claude-agent-acp` runs on the Max subscription; Symphony's Elixir
internals beyond the survey; Teamwork's role prompts (never published); the
herdr socket API in practice (CLI used throughout); Bernstein's gate and merge
paths end to end with our adapter (the first test in the design doc).

## Addendum, 2026-09-02 (evening)

Added after the herdr-adapter stages, the native spike and a full read of the
Bernstein docs set. Sources: `spike-report.md`, `stage1-report.md` through
`stage6-report.md`, `bernstein-docs-review.md`, `agy38-report.md` and
`native-migration-plan.md` in the session scratchpad.
It supersedes section 11's "herdr adapter only" line: executors and judges now
run through Bernstein's native adapters (see "Why native adapters" in
`docs/2609-02-design.md`).

### Bernstein docs vs the code we measured (`bernstein-docs-review.md`)

- **Documented, not wired for us: stream signals.** `docs/adapters/stream_signals.md`
  defines a `BERNSTEIN:<KIND>` stdout grammar as the supported way a spawned process
  reports completion. Nothing in our path emits or consumes it: native adapters
  complete through the `git-diff` output mode (commit plus process exit), and
  plan-level `completion_signals`, documented in `architecture/plans.md` with six
  types, never reach the task server because the planner omits them from the task
  POST (`stage1-report.md`).
- **Documented, rejected by the seed parser: plugin gate names.**
  `architecture/quality-pipeline.md` shows a custom gate named directly in
  `quality_gates.pipeline` and registered through the `bernstein.gates` entry point,
  and `gate_runner.py` would accept it, but `seed_parser.py` validates pipeline names
  against a hardcoded `VALID_GATE_NAMES` that ignores the registry
  (`stage1-report.md`). Our gate therefore rides the built-in `tests` step with
  `command_override`.
- **Documented and true:** per-step `cli`/`model`/`effort` in the plan
  (`workflows/per-step-routing.md`; the route is auditable in
  `.sdd/traces/<task_id>.jsonl`, not in our own argv), `--port N` with
  `.sdd/runtime/server.port` for a second run on the same host,
  `bernstein quarantine list|clear --task TITLE` in place of `rm -rf .sdd`, and
  `quality_gates.base_ref` as the knob for the gate's changed-file set.
- **Documented, true, and still not enough: `merge_strategy`.** The key is parsed
  from `bernstein.yaml` and appears in `config_snapshot.json`, but the approval gate
  is built from `.sdd/runtime/run_config.json` alone
  (`orchestrator.py:817-832`, `:7126-7134`), and nothing in the tree writes that file
  from the seed or from `--merge` (`stage2-report.md`, `stage3-report.md`). Our
  `run-config` keeps writing it.

### Contamination rule for replays

A replay measures the executor only if the answer is unreachable from its checkout.
`git worktree add` shares the parent object store, so the merged answer commit stays
reachable: the gopost 1a replay reproduced it byte for byte and measured nothing
(`stage2-report.md`). The rule, applied from the 3.8 round onward: build each replay
root with `git clone --single-branch --no-tags --branch <base>`, then
`git remote remove origin`, and verify by ancestor count and by
`git cat-file -e <answer-sha>` failing. Single-branch plus no-tags cuts the
descendant history; removing the remote stops a later fetch from bringing it back.

### Gemini 3.8 Flash (high), five cases (`agy38-report.md`)

Ranked 4th, 3rd, 3rd, 2nd and 4th in fields of four to six, 15 certain defects, never
first. It fixes 3.7's two discipline failures (a skipped lint gate on 1b, inert tests
on D) at about 1.3x 3.7's wall and 2x its fresh input tokens. The standing split is
unchanged: Opus 5 on seam and design briefs, Codex on exact-line and transfer briefs,
agy on neither.

### Judge-family caveat on cross-round ranks

Round 2 was Fable-judged and round 3 Opus-judged. On identical diffs the Opus judges
counted more defects and ranked the Opus 5 executor first in 4 of 5 cases, where Fable
ranked Codex first in 2 of 5. Ranks compare within a round only; any table that mixes
rounds is comparing judges as much as executors.

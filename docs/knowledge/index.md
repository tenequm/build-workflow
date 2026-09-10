---
okf_version: "0.2"
---

# What belongs here

Durable knowledge about the build-workflow project: decisions with their
rationale, findings with their evidence, rules with what they protect
against. Knowledge, not memory - current state (versions, in-flight work,
run results) stays in the ledger, git history, and release notes. AGENTS.md
keeps one-line laws; the rationale behind a law lives here, linked. Every
claim carries a source; a concept that stops being true is deprecated, never
deleted. Written as if this repository is public - because it is.

# Decisions

* [Workspace-at-first-write replaces the primary lock](decisions/workspace-at-first-write.md) - a build occupies only its workspace branch from the first artifact write; the 2026-09-03 repo-wide lock was dropped for it.
* [Bernstein is tracked upstream-first through a minimal rebased fork](decisions/upstream-first-minimal-fork.md) - the engine fork carries only fixes upstream does not yet have, rebuilt from upstream main whenever upstream absorbs some; every fix is submitted upstream as a small single-topic PR. Fully absorbed 2026-09-08: the workflow now installs a source build of upstream main, and the discipline stands ready if a new engine defect appears.
* [Phase ordering lives between engine runs, not inside one](decisions/phase-boundary-between-engine-runs.md) - one Bernstein run per phase, the driver owning the boundary (teardown, delivery predicate, driver-side blind judge, pinned fix mini-runs); settled 2026-09-08 after two in-DAG routing designs were falsified.

# Findings

* [Native merge-back can fetch, rebase and push the integration branch](findings/native-merge-back-pushes.md) - local completion requires stopping safe_push before any Git I/O, not merely omitting an explicit driver push.
* [Native merge evidence differs between live verification and dead-agent reaping](findings/native-merge-evidence-varies-by-path.md) - merge gates receive surrogate task IDs, dead-agent reaping can omit task_merged, and paired WAL claims need closure before a fresh phase.
* [A fix proven in our environment is not proven for stock Bernstein](findings/validate-fixes-against-stock-assumptions.md) - pre-submission adversarial validation of three locally-proven engine fixes found one that would false-positive on every clean exit in stock target repos and disproved the premise of half of another.
* [Codex turns can be silently truncated by its content filter, presenting as clean completion](findings/codex-content-filter-truncates-executor-turns.md) - benign vocabulary (race, sweep, exploit, attack) can kill a codex turn mid-task with a normal-looking ending, so an executor can exit 0 with its work incomplete; brief vocabulary is the authorable risk surface and the engine's clean-exit guards are the mitigation.
* [Bernstein releases dependents on worker-reported DONE, before any verification](findings/bernstein-done-releases-before-verification.md) - the engine's dependency model is optimistic (gates are compensating controls, not barriers), and response-cache reuse bypasses execution despite file wiping or description nonces; strict verified-before-start ordering requires keeping downstream work off the task server entirely.
* [A documented Bernstein surface is not a wired one - verify the production fire site](findings/declared-but-unwired-engine-surfaces.md) - six declared surfaces (hook bus, SSE vocabulary, DSL edges, ReviewGate, --approval/--merge, yaml plugin pipeline) execute nowhere on a plan run, while the assumed-absent test follow-up dispatcher is wired and default-ON; prove both presence and absence at the call site.
* [A merged task is archived to CLOSED, a status the quiescence self-stop does not count](findings/merged-tasks-close-and-stall-quiescence.md) - a run whose every task merged never self-stops and never journals the run_completed/run_quiescence pair the operator's phase boundary is defined by; recorded executors reach the quiescent tick while still DONE, so only the first paid build exposed it.
* [Native task bookkeeping contradicts its own delivered work](findings/engine-bookkeeping-is-not-delivery-proof.md) - across the first real builds the engine landed scored work while recording the attempt failed, refused a first attempt whose retry delivered, dropped owned_files from every retry, and left a superseded retry claimed; the phase boundary must rest on scorer receipts, merge ancestry and journal events.
* [Plan-file completion signals are silently dropped at task POST](findings/plan-post-drops-completion-signals.md) - the plan-post helper omits completion_signals from the POST body, so witnesses declared in plan YAML never reach the server via `run --from-plan` and signal-less tasks pass default verification invisibly.

# References

* [Contributing to upstream Bernstein - what its machinery actually enforces](references/contributing-to-bernstein.md) - squash-merge makes the PR body the permanent commit message, fragments must close with the PR number, new tests must fail on base, prose is scanned by a hygiene denylist, and the bisect bot's regression labels are heuristic.

# History

* [log.md](log.md) - bundle update history.

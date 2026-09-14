# Plan: the `/review-pr` run on pond#237

Reviewer C of three. See [the comparison index](README.md).

This document is self-sufficient on purpose: it is the source of truth for
executing the run, and it is written to be picked up cold, after a context
compaction, with nothing else loaded.

## Why the lane changes

The lane that was proven on 2026-09-12 was `claude-sonnet-5` as manager over
five free local qwen lenses. It worked: the smoke case recovered in 1205s, and a
real review of a 7-file governance PR recovered 11 of 14 hand findings.

Two things force a change now:

1. **Claude Max is at about 10% of the weekly quota.** The lane cannot lean on
   Claude for the reasoning-heavy half.
2. **codex limits are refreshed**, and `gpt-5.6-sol` at high effort has just
   produced [baseline B](baseline-polish-codex-5.6-sol-high.md) on this exact
   pull request, including the one blocking finding opus-5 missed. It has earned
   the judgment seat.

So the reasoning half moves to codex, the cheap half stays on the free local
gateway, and the two cheapest lenses get **shadowed** so this run also answers a
second question: can the free half stay free?

## Role is a model slot, and we name the slots

Routing in bernstein is per **role**, not per task. The lens lives in the task
text; the role decides which model executes it. The built-in vocabulary cannot
express this lane - it has one `analyst` and one `qa`, so two lenses sharing a
role would be stuck sharing a model - so the seed declares nine roles of its own,
one per lens.

That is legal because the door the manager uses validates against the seed and
nothing else: `core/routes/task_crud.py` rejects a role that is not a
`role_model_policy` key with a 400 that names the valid ones. `KNOWN_ROLES` gates
the MCP `create_subtask` tool and the plan-step schema, and a manager posting by
curl reaches neither. `manager` is the one name we do not choose - the engine
tests that literal string in three places.

The run also ships `.bernstein/templates/roles/` with **no** `skills/` directory,
which is what keeps the engine's own role list out of every agent's context. The
full mechanism, the measurements and the trap in a partial override are in
[the knowledge base](../../knowledge/findings/role-vocabulary-leaks-into-every-agent.md).

## The lane

| Step | Role | Model | Counted in report? |
|---|---|---|---|
| Plan, create tasks | `manager` | codex `gpt-5.6-sol` (high) | - |
| Lens 1: claim vs implementation | `lens-1-claim` | codex `gpt-5.6-sol` | yes |
| Lens 2: side-effect gating | `lens-2-side-effects` | codex `gpt-5.6-sol` | yes |
| Lens 3: design and reuse | `lens-3-design` | codex `gpt-5.6-sol` | yes |
| Lens 4: efficiency | `lens-4-efficiency` | local qwen `flash-next` | yes |
| Lens 4: efficiency | `lens-4-efficiency-shadow` | agy `gemini-3.7-flash-medium` | **shadow** |
| Lens 5: cleanliness | `lens-5-cleanliness` | local qwen `flash-next` | yes |
| Lens 5: cleanliness | `lens-5-cleanliness-shadow` | agy `gemini-3.7-flash-medium` | **shadow** |
| Write the report | `report-writer` | codex `gpt-5.6-sol` | yes |

9 agents: 5 codex, 2 qwen, 2 gemini. **`claude-sonnet-5` is out of the lane
entirely** - it was to have carried two shadow tasks, and with Claude Max at
about 10% of the weekly quota the operator dropped it on 2026-09-14. The manager
moved to codex in the same decision, so this lane spends no Claude quota at all.

**The shadow design is symmetric by design.** Lens 4 and lens 5 each run the
*identical* task text on two models in parallel. Nothing about the prompt
differs; only the executing model does. The seven lens role templates are
byte-identical for the same reason - a prompt that differed between a lens and
its shadow would measure the prompt instead of the model.

Shadows write `shadow-lens-4.md` / `shadow-lens-5.md` into the run's scratch
directory, and the goal text tells the report writer to ignore every `shadow-*`
file, so they cost nothing in the review output and remain on disk for the diff
afterwards.

Lenses 1-3 are the expensive, judgment-heavy ones and are not shadowed:
shadowing the strongest step teaches nothing actionable, while shadowing the free
lenses answers a question with a decision attached to it.

## Steps

Steps 1 and 2 are **done** and committed (`aafffe3`, `9dd5038`, `0352f6f`).

1. ~~Seed edit~~ - nine custom roles in `role_model_policy`, plus the note on why
   the names are ours. **Done.**
2. ~~Goal edit~~ - a lens-to-role table, the two shadow tasks, and the `shadow-*`
   exclusion rule for the report writer. Also: a role template per role under
   `skills/review-pr/templates/bernstein-templates/roles/`, copied into the run's
   workdir by both `SKILL.md` and `harness.py`; and a `codex` PATH shim carrying
   `-c model_reasoning_effort=high`. **Done.**
3. **Proof on the corpus.** The goal text changed, so the standing rule is the
   full four cases - but the smoke runs first, because a broken goal does not fail
   fast: the ledger records case-01 ERRORing at 4699s and 6742s before a 1205s
   green run. Run the cheap proofs with `REVIEW_CODEX_EFFORT=low`, which pins the
   shim's effort down for a plumbing test; a verdict scored at `low` is not
   comparable to one at `high` and is never a ledger claim. Then cases 02 and 04
   alongside the pond run at `--jobs 1`, which keeps two bernstein runs in flight
   and no more.

   **Mechanism is proven, on the real lane** (2026-09-14, case-01 at low effort,
   575.3s - the fastest path-A run on record): nine tasks under the nine custom
   roles, codex as manager, codex lenses and report writer, both gemini shadows
   writing `shadow-*` files, the report at the contract path, the trailing json
   block parsing, zero ERROR. Two failures were found and fixed getting there -
   a partial templates override that made every lens role unreassignable, and the
   codex sandbox denying loopback - and one rule was found missing, that a finding
   must name its identifier.

   **Shadow exclusion is now proven too** (2026-09-14, case-03): both gemini
   shadows wrote roughly a kilobyte each, both naming the planted injection, and
   neither reached the report. The filter had something to exclude and excluded
   it.

   **A third smoke found the last defect, and it was in the grader.** case-01
   failed a third time while its reviewer was correct a third time: the name was
   in the prose and in an `identifier` key the model invented, and the grader was
   grepping the block's `claim`, which had been paraphrased down to a sentence
   without the name. Two fixes followed, in `8f350d3` - `identifier` became a
   required field compared exactly, and a block that breaks the contract now
   scores MALFORMED instead of MISSED, carrying `would_be` so the two are never
   confused again. Both reasons are in the knowledge base
   ([the name](../../knowledge/decisions/findings-name-identifiers.md),
   [the rejection](../../knowledge/decisions/grader-fails-closed-on-a-broken-block.md)).
   The goal text changed again, so the four-case proof re-ran.

   **The four-case run then found the same defect a third time, in the category
   slot.** case-01 recovered in 335.3s with zero extra findings and no case
   produced a MALFORMED block, so both fixes above are proven. But case-02 and
   case-03 each found, named and blocked their planted defect and filed it as
   `cleanliness`, which neither case accepts - and case-03's identical finding had
   scored `correctness` one run earlier, so it was a coin flip. The goal text
   listed five legal categories and no rule for choosing one, and the fifth,
   `convention`, had no section in the report a reviewer could reach. `4a25b17`
   states the routing - everything untrue is `correctness`, `cleanliness` is
   tidiness in code that behaves correctly, ties break toward the earlier label -
   and drops `convention` from both the goal text and the grader. All four cases
   now accept exactly one category.
   [The finding](../../knowledge/findings/a-category-enum-without-a-routing-rule-is-a-coin-flip.md)
   generalises it: an enum offered without a routing rule is chosen at random, and
   a label with no home in the output template is never chosen at all.
4. **Run pond#237** per `skills/review-pr/SKILL.md`: throwaway checkout at the PR
   base, the two `gh` reads first, then `git remote remove origin`, then the
   templates copy, then the PATH shims, then `bernstein run`.
5. **Compare four ways** and write up recovered / missed / novel into
   `comparison.md` beside this file.

## Grading rules

Fixed in [the index](README.md) before the run so the bar cannot move afterwards.
The short form: compare by substance not by line anchor; score recovered /
missed / novel against the union of A and B; **the Pi `sqlite_path` blocking
finding is the single most important cell**; novel findings are judged true /
false / unfalsifiable and a false one costs more than a missed cleanliness item;
every miss the operator would have acted on becomes a new corpus case.

"Compare by substance, not by anchor" is what forced every finding to name its
identifier: C reads a checkout at the base and A and B read the head tree, so no
line number is shared and the name is the only thing left to match on. C's
findings carry it in an `identifier` field of the report's json block, which is
what makes the four-way comparison a lookup rather than a reading exercise. The
reasoning is
[in the knowledge base](../../knowledge/decisions/findings-name-identifiers.md).

## Facts that cost time to learn

Do not re-derive these.

- **Codex effort has no dedicated flag, but it does have `-c`.** The run's
  `codex` shim passes `-c model_reasoning_effort=high`, which pins the effort to
  the run instead of to `~/.codex/config.toml`. Bernstein cannot carry it: the
  adapter builds argv with no hook, `CODEX_HOME` is stripped by the env
  allowlist, and `role_model_policy.<role>.effort` parses and is then dropped
  unread. Keep the value a literal - codex accepts a misspelling and reports it
  back as the effort, even under `--strict-config`, so an interpolated typo would
  downgrade the lane in silence. Full mechanism in
  [the knowledge base](../../knowledge/findings/codex-effort-is-per-invocation.md).
- **The shims isolate `pi` and `claude` only.** The `codex` shim pins effort and
  adds no isolation, so `codex` and its `.codex/`, and `agy` and its `.agy/`,
  still read the reviewed tree (`AGENTS.md` included). pond is the operator's own
  repository, so this lane is safe here and is **not** reusable on a third-party
  repository until those two are isolated as well.
- **The templates copy is load-bearing and must cover every role.** Ship
  `.bernstein/templates/roles/<role>/system_prompt.md` for all nine and no
  `skills/` directory. Ship only `manager/` and the orchestrator's reassign
  correction silently skips every lens role - a log warning, never a failure.
- **The local gateway has three models, all 262144 context**: `qwen3.8-flash-next`
  at 209 tok/s (the fastest available - there is nothing quicker to switch to),
  `qwen3.8-27b-nvfp4` at 78 tok/s (dense, stronger per token),
  `qwen3.6-35b-a3b-nvfp4` at 54 tok/s. Never read or print the API key in
  `~/.pi/agent/models.json`.
- **Do not raise `--jobs` past 2** on the local lane: four in flight drew 429s on
  36 of 67 sessions.
- **A worker's uncommitted files do not cross the worktree boundary**, and
  `bernstein memory` facts are worktree-scoped and die with the worktree. The only
  channel that crosses is one scratch directory outside every repository,
  `mktemp -d` by the lead before any task is created and quoted verbatim in every
  worker's task text.
- **A misfiled finding is not a missed defect either.** MISFILED means the reviewer
  found it and put it in the wrong category. After `4a25b17` the routing is stated
  and every case accepts exactly one label, so a MISFILED row now means the routing
  rule failed to reach the reviewer - not that the taxonomy is ambiguous.
- **A malformed json block is not a missed defect.** The grader rejects a block
  short a required field rather than scoring it MISSED, and the row says what the
  verdict would have been. When reading pond#237's output, a MALFORMED row means
  fix the block and re-read, never "the lane missed it".
- **The report has exactly one correct location**: the checkout the run started
  in, which from inside a worktree is `$(dirname "$(git rev-parse --git-common-dir)")`
  and is the same command in the checkout itself.
- **Never attach a working-tree acceptance check** (`git status` empty, N entries).
  The orchestrator keeps runtime state inside the checkout, so such a check fails
  every worker forever and destroys the report it was meant to protect.
- **The engine pushes on its own**: `git push origin` on every agent merge and on
  salvage. Stripping the remote is the countermeasure, and it is why
  `git remote remove origin` is in the invocation.
- **Residual, unfixed**: the engine cannot observe a pi agent's liveness (pi
  writes nothing to a redirected stdout until its turn ends), so it judges working
  agents dead. Four to seven tasks fail and retry per run. This costs wall clock,
  not the deliverable. **Do not treat "zero failed tasks" as a pass bar.**
- **A run ends only at a `/proc` cwd sweep**: `harness.sweep(pathlib.Path(dir))`
  (a `Path`, not a `str`). The CLI returning means nothing.
- **Launch long runs `setsid`-detached** (`setsid nohup ... & disown`); the
  harness's background-task supervisor kills them when the host hits a transient
  low-memory spike.

## The standing bar

Unchanged by this plan. The smoke case (`just eval case-01-off-by-one`, about 20
minutes) after any engine, seed or host change; all four cases only when the goal
text changes. Every run appends one row to `docs/review-ledger/evals.jsonl`; rows
carrying `"corpus": "v2"` are the comparable ones.

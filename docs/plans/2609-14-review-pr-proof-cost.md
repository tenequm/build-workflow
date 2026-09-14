# Cut the cost of proving a /review-pr change

A record of a decided plan, not direction to a future agent. It is written to be
picked up cold.

Status (2026-09-14): all four work packages are complete.

## The problem this solves

At planning time, `/review-pr` had no grader test suite. The four-case corpus run
was its only regression signal, so every change paid the same 15-20 minutes
regardless of size - including changes that altered no model judgment at all.

That price is misallocated. Across four corpus rounds the planted defect was
detected in **16 of 16 case-runs**. Every failure was the json block disagreeing
with the grader: the name absent (`88feb83`), the block unvalidated (`8f350d3`),
the category unrouted (`4a25b17`), the name qualified (`9f01acb`). Not one was a
model failing to find a defect. The class that keeps breaking is a pure-function
contract that needs no model to test.

## Preconditions

Do not start until all three hold:

1. **No corpus run is in flight.** `pgrep -f review-pr-cases/harness.py` is empty.
   The harness copies role templates per case at case setup
   (`fixtures/review-pr-cases/harness.py:212`), so editing a template mid-run hands
   later cases a different pipeline than earlier ones and silently invalidates the
   proof.
2. The working tree is clean and the ledger row for the run that just finished is
   committed.
3. `just operator-check` passes before any edit, so a
   later failure is attributable.

Work the packages in order. WP2 is what makes WP3's cheap proof legitimate.

## WP1 - a model-free grader test - DONE (`5b4a8aa`)

**Highest value, and it needs no corpus run to be believed: it changes nothing the
pipeline reads.**

The grading surface in `fixtures/review-pr-cases/harness.py` is already pure
functions over dicts - no models, no subprocess, no disk:

| Function | Line | Takes |
|---|---|---|
| `violations(summary)` | 277 | the parsed json block |
| `score(case, summary)` | 303 | a case dir and the block |
| `adapt(finding)` | 503 | one finding |
| `anchored(finding, expected)` | 241 | finding + case expectation |
| `names(finding, expected)` | 255 | finding + case expectation |
| `mentions(finding, keywords)` | 229 | finding + keyword list |
| `accepted_categories(expected)` | 216 | case expectation |

Constants to assert against: `VERDICTS` (75), `REQUIRED_FINDING_KEYS` (129),
`ACTIONS` (131).

Write `bernstein_operator/tests/test_review_grader.py`. pytest is already
configured there (`[tool.pytest.ini_options]`, `testpaths = ["tests"]`) and
`harness.py` is already inside that project's `ty` surface, so there is precedent
for reaching across - follow whatever `tests/conftest.py` already does for paths
rather than inventing a new mechanism.

Cover, at minimum, one frozen fixture per historical failure plus the happy path:

1. A valid block scores RECOVERED.
2. A block missing a required key is MALFORMED, never MISSED - the distinction the
   grader exists to make.
3. A finding whose `category` is outside the four is MALFORMED.
4. An `action` outside `ACTIONS` is MALFORMED.
5. A qualified `identifier` (`page_count()`, `mod.page_count`) does not match a
   bare expected name - the `9f01acb` regression.
6. A correct finding filed under the wrong category is MISFILED, not MISSED.
7. A block that is absent entirely is MISSED.

Build the fixtures as literal dicts in the test file. Do not add a fixtures
directory: if it can be inlined, inline it.

**Proof:** `just test` green, then the full
`check`. No corpus run.

**Outcome:** twelve model-free tests now cover `score`, `violations`, `anchored`,
`names` and `adapt`, including every historical report/grader contract failure. The
suite runs in milliseconds and the full check passed when it landed.

## WP2 - a third proof tier - DONE (`32c41c1`)

At planning time, the project instructions had two tiers: an engine, seed or host
change re-ran the smoke case alone; a change to the goal text ran all four. Nothing
covered a change that moved a rule between files without altering what any model
judged - and that is what `67ea13b` was, which paid the four-case price for a
transmission change.

Add the third tier to the corpus paragraph in `CLAUDE.md`. Shape it as a rule with
a test, not a sentence of advice: a transmission-only change is one where the
before and after text of every model-facing prompt is identical modulo which file
carries it, and it proves on one case. If that identity cannot be demonstrated, it
is not transmission-only and the existing tiers apply.

Name WP1's test as the thing that now carries the contract, so the tier is not a
weakening: the four-case run stops being the only guard against a contract
regression.

**Proof:** documentation only, no model reads it. `check` green.

**Outcome:** `AGENTS.md` now defines the transmission-only tier by prompt-text
identity, requires the four-case tier when that identity cannot be shown, and names
WP1's grader tests as the contract guard. The full check passed when it landed.

## WP3 - measurements outside the reviewer

The original package proposed keeping dormant shadow routes and role templates in
the production skill. Implementation review rejected that design: a shadow is a
measurement of the reviewer, not part of the reviewer. Even dormant model routes,
role directories, report exclusions and re-enable instructions couple production
workflow files to an experiment and make model-routing changes touch agents that do
not need to know the experiment exists.

That opt-in design is superseded. Production has exactly seven roles: one mechanical
coordinator, five lens executors and one report writer. It contains no shadow role,
route, task, dependency rule or model-facing shadow vocabulary. The Pond comparison
remains useful evidence, but any future comparison runs out of band: invoke the
candidate model separately over the same lens text and compare its artifact after the
production review. It must not alter production tasks or report inputs.

The boundary is executable rather than advisory:

- `scripts/review_prompt_boundaries.py` requires exactly the seven production role
  directories and seed routes, byte-identical generic lens executor prompts, and no
  measurement or routing vocabulary in model-facing text.

Commit `711f340` records the intermediate all-four run after in-band shadows were
removed: all four cases RECOVERED with no failed task and the seven-role/five-edge
shape observed in every workspace. Because the later cleanup changes model-facing
prompts, that row is supporting evidence, not the final proof.

**Final proof:** commit `f9c42e5` records the four-way run against clean revision
`90929c4`. All four cases were RECOVERED, no task failed, and every cleanup sweep
reported zero survivors.

## WP4 - four concurrent eval jobs - DONE (`a303b5f`, `52e5589`, `beedc54`)

The original blocker was based on a false premise: `TMPDIR` does reach workers. It
is passed through Bernstein's environment allowlist, and codex grants it as a writable
root under `workspace-write`, including when it is outside the workspace.

The harness now creates its default workspace under
`~/.cache/review-eval/<stamp>`, creates `<work>/tmp`, and exports that directory as
`TMPDIR`. Workspace and worker scratch therefore use the same large filesystem. It
keeps the 10 GB per concurrent case floor and checks both locations, so an explicit
`--work` split still fails safely when either side lacks headroom.

The default is now `--jobs 4`. A four-case run completed at that concurrency and was
recorded in the ledger by `52e5589` with no ERROR or MALFORMED result. The later
`beedc54` cleanup corrected the remaining copies of the old hardcoded-`/tmp` claim.

## Tooling - load the `python-dev` skill before writing WP1

WP1 is Python. Load the `python-dev` skill and follow its stack rather than
improvising: this repository already runs exactly that stack, so there is nothing to
set up and nothing to migrate.

What it means concretely here:

- **Run everything through `uv run`.** Never a bare `pytest`, never a system
  interpreter. The root `Justfile` wraps it with `test` and `operator-check`.
- **pytest is already configured** in `bernstein_operator/pyproject.toml` with
  `testpaths = ["tests"]`, `python_files = ["test_*.py"]` and strict settings. Do not
  add a second pytest config, a `pytest.ini`, or a `setup.cfg`.
- **ruff and ty own style and types.** Do not hand-format, do not add type-ignore
  comments to silence `ty`, and do not write a `select` list into the ruff config -
  ruff 0.16 enables 413 rules by default and a `select` list would make it weaker.
- **Code minimalism applies to tests too.** Frozen report fixtures are literal dicts
  in the test file. No `fixtures/` directory, no factory helpers, no parametrize
  indirection that hides which case is which. A reader should see the bad block and
  the expected verdict on the same screen.
- **Comments follow the repository's rule**: explain a *why* that the code cannot,
  never a *what*. A test named `test_missing_required_key_is_malformed_not_missed`
  needs no comment explaining that it checks a missing key; it may need one sentence
  on why MALFORMED and MISSED must not be conflated.

## Hard constraints

- Never `--no-verify`, never amend an existing commit, never force-push. After a
  hook failure the commit did not happen: fix, re-stage, make a NEW commit.
- Conventional Commits.
- `skills/` and `templates/` changed means the release is `just ship`, not a bare
  push - and only from `main`, only after every package's proof is green. If only
  WP1 and WP2 land, they are doc and test changes and may push without shipping.
- The harness is linted by `bernstein_operator`'s ruff config, not
  `bernstein_herdr`'s. The gate is
  `just operator-check`.
- `docs/knowledge/index.md` is generated: after any concept change run
  `python3 scripts/kb_index.py` and require `--check` to pass.
- A retro item closes as a check, a template field, or a test - never as another
  skill sentence. WP1 is a test, WP2 is a rule with a test behind it, and WP3 is a
  static production-role boundary check. None of them is advice.
- Report what actually happened. A package that does not reach green is reported as
  not green, with the output.

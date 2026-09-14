# Cut the cost of proving a /review-pr change

A record of a decided plan, not direction to a future agent. It is written to be
picked up cold.

## The problem this solves

`/review-pr` has no test suite. The four-case corpus run is its only regression
signal, so every change pays the same 15-20 minutes regardless of size - including
changes that alter no model judgment at all.

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
3. `just --justfile bernstein_operator/Justfile check` passes before any edit, so a
   later failure is attributable.

Work the packages in order. WP2 is what makes WP3's cheap proof legitimate.

## WP1 - a model-free grader test

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

**Proof:** `just --justfile bernstein_operator/Justfile test` green, then the full
`check`. No corpus run.

## WP2 - a third proof tier

`CLAUDE.md` today has two tiers: an engine, seed or host change re-runs the smoke
case alone; a change to the goal text runs all four. Nothing covers a change that
moves a rule between files without altering what any model judges - and that is
what `67ea13b` was, which paid the four-case price for a transmission change.

Add the third tier to the corpus paragraph in `CLAUDE.md`. Shape it as a rule with
a test, not a sentence of advice: a transmission-only change is one where the
before and after text of every model-facing prompt is identical modulo which file
carries it, and it proves on one case. If that identity cannot be demonstrated, it
is not transmission-only and the existing tiers apply.

Name WP1's test as the thing that now carries the contract, so the tier is not a
weakening: the four-case run stops being the only guard against a contract
regression.

**Proof:** documentation only, no model reads it. `check` green.

## WP3 - shadows opt-in

Shadows are a measurement, not a verdict input: the goal text forbids a `shadow-`
finding from entering the report, the counts, or Dropped. On a corpus case with a
planted defect they contribute nothing and cost 8 of 36 agents per four-case run.

They are still valuable on real pull requests - the pond#237 run is the evidence,
where the gemini lens-5 shadow returned "No cleanliness defects found" against
twelve findings from its primary. **So make them opt-in, never delete them.**

The cheap mechanism: the `roles:` map in `review-seed.yaml` is inert routing
config, and a role nobody creates a task for costs nothing. What actually spawns a
shadow is the role table and the shadow paragraph in
`skills/review-pr/templates/review-goal.md`. Remove those two rows and that
paragraph to turn shadows off; the seed entries and the two shadow role templates
stay in the repository so turning them back on is restoring one table and one
paragraph.

Before editing, `rg -n 'shadow' skills/ fixtures/ docs/knowledge/ CLAUDE.md` and
handle every hit deliberately. Two that must survive in some form: the
report-writer still ignores `shadow-` files (harmless and correct when none exist),
and `report-writer` must never list a `-shadow` task in `depends_on` - that rule is
load-bearing and is why run 1 died
([the quarantine finding](../knowledge/findings/quarantine-makes-a-resource-outage-permanent.md)).

Record in the commit body how to re-enable them, and say plainly that the pond
shadow comparison is the reason they exist.

**Proof:** this changes which agents the manager creates, so it is engine-shaped,
not transmission-only: `just eval case-01-off-by-one`, which passes only as
RECOVERED with zero failed tasks and a clean sweep. One case, not four.

## WP4 - jobs, blocked on disk. Do not attempt.

`harness.py:924` computes `needed_gb = DISK_FLOOR_GB * jobs` with
`DISK_FLOOR_GB = 10` (line 79). `jobs=4` needs 40 GB and `jobs=3` needs 30 GB.
`/home` had **26 GB free** when this plan was written, so both are refused by the
guard before a single agent starts. Raising concurrency would cut a four-case run
from about 20 minutes to about 13, and it is unavailable until roughly 14 GB is
freed.

Do not lower `DISK_FLOOR_GB` to make the number fit. That floor exists because run
1 of the pond#237 evaluation died when `/` reached 0.3 GB free and every starved
task quarantined permanently. Report the blocker; do not route around it.

## Tooling - load the `python-dev` skill before writing WP1

WP1 is Python. Load the `python-dev` skill and follow its stack rather than
improvising: this repository already runs exactly that stack, so there is nothing to
set up and nothing to migrate.

What it means concretely here:

- **Run everything through `uv run`.** Never a bare `pytest`, never a system
  interpreter. `bernstein_operator/Justfile` already wraps it: `test` and `check`.
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
  `just --justfile bernstein_operator/Justfile check`.
- `docs/knowledge/index.md` is generated: after any concept change run
  `python3 scripts/kb_index.py` and require `--check` to pass.
- A retro item closes as a check, a template field, or a test - never as another
  skill sentence. WP1 is a test, WP2 is a rule with a test behind it, WP3 is a
  template field. None of them is advice.
- Report what actually happened. A package that does not reach green is reported as
  not green, with the output.

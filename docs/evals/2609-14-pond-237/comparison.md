# Reviewer C against A and B - pond#237

Reviewer C is `/review-pr` (stock `bernstein run`, nine tasks, five numbered lenses plus
two shadows, manager on `claude-sonnet-5`, lenses mixed local-qwen and codex at `high`).
A and B are the two `/polish` baselines committed beside this file, captured before the
run so the bar could not move afterwards. Grading rules are in [README.md](README.md).

**Mechanism and content are scored separately**, because they diverged: the lenses did
their work and the run could not deliver it.

## Verdict

**C passes the decisive cell and fails the sweep.** It found the Pi `sqlite_path`
regression - the one blocking defect in the PR, which A's 28 findings missed and only B
caught - independently in two lenses, both at P1. It recovered 8 of the 37 union rows,
missed 29, and contributed 19 findings neither baseline has, of which seven are verified
true against the patched source and none is verified false.

| | A (opus-5 high) | B (codex 5.6-sol high) | C (/review-pr) |
|---|---|---|---|
| Findings | 28 | 6 headline / 14 claims | 27 |
| Blocking regression | missed | **found** | **found, twice** |
| Union rows recovered | - | - | 8 of 37 |
| Novel vs A+B | - | - | 19 |
| Novel verified true | - | - | 7 (none false) |
| Deliverable produced | yes | yes | **no** |

C's profile sits close to B - correctness-weighted, few cleanliness items - with far more
efficiency depth than either baseline. Where A swept comments and test hygiene, C traced
call graphs.

## The decisive cell

Rule 3: *a reviewer that misses the Pi `sqlite_path` regression has failed this PR
regardless of how many cleanliness items it collected.*

C did not miss it. Lens 1 (correctness) and lens 3 (design) raised it independently, both
P1, both naming `missing_source_root` at `packages/pond/src/main.rs:5237` and both citing
`adapter/pi_coding_agent.rs:127-134` and `:463-468` for the `sqlite_path` chain that the
generic `path` preflight cannot see. Lens 1 additionally traced it into the all-absent
short-circuit at `main.rs:4119-4165`, which makes the same mistake one branch earlier -
a consequence B's write-up does not reach.

Two independent lenses converging on the one blocking finding is the single strongest
signal in this run. It is also the finding a 28-item cleanliness sweep did not produce.

## Recovered - 8 union rows

| Union row | Finding | Where C raised it |
|---|---|---|
| 30 | `source_root` - Pi's reachable SQLite source discarded when `path` is absent (B's blocking) | lens 1 P1, lens 3 P1 |
| 2 | `resolve_adapters` - a mistyped adapter name with an absent path exits 0 as `source_missing` instead of failing as unknown | lens 1 P2 |
| 6 | `run_sync` - explicit-source validation goes stale; lock, store creation and the ~500 MB embedder all precede the recheck | lens 2 P2 |
| 7 | the all-absent short-circuit hand-copies the ok document the shared tail already builds | lens 5 F8 |
| 10 | `bail_when_explicit_source_missing` carries an always-true bool **and** re-stats the disk | lens 5 F5 (the bool), lens 4 F4 (the re-stat) |
| 20 | three TOML fixtures bake 13 literal spaces from a broken line join | lens 5 F9 |
| 8 (partial) | `has_adapters` re-resolves config that `local.adapters` already carries | lens 4 F4 |
| 33 (partial) | the plan doc carries agent-control directives into permanent documentation | lens 3 P1, lens 5 F1 |

Row 10 is recovered by two different lenses each taking one half of A's two-part claim,
which is the same convergence pattern as the blocking finding.

Row 33 is partial: C recovered the agent-directive half in full - lens 5 quotes six
separate directive lines and names the injection shape explicitly - but neither lens
flagged the plan doc's factual error that every adapter has one scalar path. C attacks
that claim where it is executable (`main.rs`) and not where it is written down.

## Missed - 29 union rows

Three misses are worth more than the count.

**Row 1 (A and B both, the highest-agreement row).** At `main.rs:4137` the all-absent
branch calls `emit_source_missing(...)?` **before** `report.failed_adapters.push(failed)`
and before `write_last_sync`, so a stderr failure erases the record. C missed this site.
What makes it notable rather than embarrassing: the per-adapter loop 1100 lines down gets
the ordering right, with a comment saying why ("Record before emitting: the entry must
reach the JSON summary even when the stderr write fails"), and C found a *different*
defect at that corrected site - see novel N3. C read the hazard class more deeply than
either baseline and looked at the wrong one of the two sites.

**Row 4 - C scored it as a win.** A calls `main.rs:4461-4471` a correctness defect: the
new gate silently disables deletion detection for every openclaw root whenever any pass is
degraded, so one corrupt file hides the erase-pending report permanently. C read the same
lines and filed them under "Credited wins (read, not asserted)" as an efficiency
improvement. This is a direct disagreement on the same code, not an oversight, and it is
the clearest single case where the efficiency framing cost C a correctness finding.

**Row 15 - inside C's own strongest lens.** `serve --with-sync` builds the freshness rowmap
before classifying all sources as absent, defeating the PR's own optimization on the
recurring server path. A rated it `fix`, B `medium`. C's lens 4 produced six findings and
four nits about exactly this class of wasted work and did not reach this one.

The remaining 26 are A's cleanliness sweep (rows 21-29), B's smaller cleanup items
(31, 32, 34), the pre-existing follow-ups (35, 36, 37) and rows 3, 5, 11-14, 16-19. Two
of those are considered non-findings rather than blind spots: C explicitly evaluated
`expand_home` going `pub` (row 31) and the `find_session` N+1 in `reconcile_deletions`
(row 36) and declined both in writing, the second with a reason ("`deleted` is normally
empty").

Row 19 is the one cleanliness miss that matters: `row["plan"].is_null()` is a vacuous
assertion - status rows have no `plan` key - so the behavior it claims to test is untested.
Both baselines caught it. C's lens 5 ran a mechanical scan, published a coverage table of
nine checks, and declared every one clean; the scan has no check for an assertion that
cannot fail.

## Novel - 19 findings

Rule 4: each judged true, false, or unfalsifiable; a false one costs more than a missed
cleanliness item. Seven were verified directly against the patched `main.rs`. **None was
found false.**

| # | Finding | Severity | Verdict |
|---|---|---|---|
| N1 | `pond status` on an uninitialized store now walks every configured transcript tree and opens every adapter DB, per adapter, serialized - because `pending_known` is false, so every adapter falls through to `opened.discover()`. The JSON never-synced document also gains up to two synchronous subprocess spawns | medium | **true, verified** |
| N2 | the health verdict omits `IngestSummary::dropped_events` entirely, so two records with one message id and different bodies lose the second body and still report healthy - contradicting base rule `adapter-integrity-dedup` | P2 | **true, verified** |
| N3 | the two new report lines inside the per-adapter loop propagate with `?`, so a BrokenPipe on stderr calls `std::process::exit(0)` mid-sync - no summary, no last-sync record, exit 0 - and any other stderr error skips every remaining adapter | medium | **true, verified** |
| N4 | the attribution lines have no change detection: N identical red lines every tick, ~288 ticks/day, appended to an unrotated `sync.log`, and `-q` cannot gate them because the CLI arm writes through `output_err` rather than `tracing` | low | **true, verified** |
| N5 | `push()` immediately followed by `if let Some(x) = ...last()` - an unreachable `None` arm, twice | low | **true, verified** |
| N6 | `emit_degraded`'s `Option<&MultiProgress>` has one call site and it passes `Some` | nit | **true, verified** |
| N7 | a `DegradedAdapter` with four clones is constructed on every adapter pass and discarded whenever `summary_line()` returns `None`, i.e. on every healthy pass | nit | **true, verified** |
| N8 | per-adapter enumeration is awaited sequentially, so N1's cost is the sum and not the max, while the same command already fans seven store reads out with `try_join!` | low-med | true (source cited, not re-run) |
| N9 | `deleted_archive_ids` stats then opens; `is_dir()` returns false on an unreadable **parent**, classifying a permissions failure as "no archives here" - the exact ambiguity the new `Err` arm exists to surface. The cheap probe also runs after the per-agent SQLite open | low | true (source cited) |
| N10 | the dry-run success line still says "nothing written to the store" while `open_store` materializes a fresh destination - which the PR's own spec edit now admits | P2 | true (source cited) |
| N11 | `docs/spec.md` gains its only issue-number citation in the file, pointing at an unfixed defect, inside normative text | low | true (verifiable by grep) |
| N12 | the plan doc's appended 2,481-character `Addendum:` reverses three of its own numbered decisions in a section headed "do not relitigate" | low | true (source cited) |
| N13 | one spec bullet goes from 314 to 780 words on a single 5,112-character line, mixing normative posture with plan-doc rationale | nit | true (measurable) |
| N14 | `adapter/mod.rs:362-364` documents the new variant as visible at "debug" verbosity; the record that carries the reason is `tracing::info!`, i.e. `-v` | nit | true (source cited) |
| N15 | the new empty-`path` refusal is the third near-duplicate message and the only one without the blast radius the function's own comment requires of every message | nit | true (source cited) |
| N16 | the "keep the first reason" idiom is now copied five times in one file | nit | true (source cited) |
| N17 | `error.to_string()` allocated twice per skipped file | nit | true (source cited) |
| N18 | `first_unreadable_reason` retains a second copy of a string the in-flight slot already holds | nit | true (source cited) |
| N19 | the `Unimportable` reason clone survives only for a `tracing::info!` arm that is off at the default level | nit | true (source cited) |

N1 is the highest-value novel finding in the run and the one that justifies the lane. It
is a performance regression on the most corpus-sensitive command, on the host with the
largest corpus and the least reason to pay for it (a fresh install before its first sync),
in a repository that has measured and documented this exact class of cost before. Neither
baseline found it. Verified from source: the never-synced branch calls `local_status` for
**both** output formats, and inside it `pending_known` is false on an uninitialized store,
so `plan` is skipped and every enabled adapter reaches `opened.discover()`.

N3 is the second. A and B both found the stderr-ordering hazard at one site; only C found
that the surviving site can end a sync at **exit 0**, which turns a data-loss event into a
clean-looking cron record - the same silence class the PR exists to eliminate.

## Mechanism check - `high` effort in-lane, first time

Reported separately from the content verdict, per the plan.

**Pass on production, fail on assembly.** All nine tasks reached `done` and all seven lens
files were written - 46 KB of findings - and then the report writer could not deliver
them. Four attempts, one of which burned 1,949,221 input tokens against a filesystem it
could not write to. Cause: `codex --sandbox workspace-write` grants the worker's own cwd
plus a fixed list of system roots that includes `/tmp` but not the checkout root, and this
run's checkout was moved off `/tmp` by the disk guard added after run 1. One guard's fix
removed another guard's unstated precondition. The corpus could not have caught it because
every corpus workspace lives under `/tmp`, where the grant is free. Fixed in `c67d0b8`
(explicit `writable_roots` grant plus a zero-token preflight probe that refuses the lane);
the durable lesson is in
[a sandbox default grant makes location load-bearing](../../knowledge/findings/a-sandbox-default-grant-makes-location-load-bearing.md).
Evidence in [run-2-undelivered/](run-2-undelivered/).

**`high` effort holds in-lane.** This was the first run with the effort string reaching a
real lane rather than a shim test, and the output is the evidence: lens 4 produced 21 KB
and lens 5 16 KB, both with end-to-end call-graph tracing, both citing base-branch
precedent for the conventions they invoke, and both correctly refusing to run any
validation command from the PR's own tree. Lens 4 applied the diff to a scratch copy
outside every repository to read post-change functions rather than reconstruct them from
hunk context, and said so, with the line-number caveat. Lens 5 published an auditable
nine-check coverage table and a verified dead-code section.

**Both lenses reported the prompt-injection attempt without acting on it.** The plan doc's
agent-directed prose ("Do NOT commit or push", "work in THIS worktree only") was filed as
a finding by lens 3 and lens 5, and lens 4 noted separately that the PR body's
self-certification density ("18 checks, 0 deviations", "CONFIRM x6") is the shape a
downstream agent can mistake for evidence, and that its own findings are independent of
it. Neither the never-commit constraint nor the base-branch rule was breached.

## Shadow comparison - gemini against the free qwen lenses

Both shadows ran identical task text to their numbered counterparts. Neither reached the
report, by construction.

| | primary | shadow | outcome |
|---|---|---|---|
| Lens 4 | 21,250 B, 6 findings + 4 nits | 2,280 B, 2 findings | shadow found a strict subset |
| Lens 5 | 16,602 B, 12 findings | 1,842 B, **0 findings** | shadow false negative |

Shadow 4's two findings are both correct and both already covered: its P2 is union row 6
(which the primary raised in lens 2), and its P4 is the `has_adapters` redundancy inside
the primary's F4. It added nothing and got nothing wrong - a clean subset at one tenth the
volume.

Shadow 5 is the result worth keeping. It returned **"No cleanliness defects found"** and
backed it with a confident six-dimension coverage list, on a PR where the primary lens
found twelve cleanliness items and baseline A found thirteen. The failure is not that it
missed them; it is that its coverage list reads exactly like the primary's and asserts the
opposite conclusion. A shadow that reports absence in the same register as presence is not
a usable second opinion, and this is the argument for keeping shadows contractually
excluded from the report rather than merged into it.

## What becomes a corpus case

Per rule 5, every miss the operator would have acted on becomes a case in
`fixtures/review-pr-cases/`. Two candidates, in order:

1. **Row 4 - a defect scored as a win.** C read `main.rs:4461-4471`, understood it, and
   filed it under credited wins while A filed it as a correctness defect. A case that
   plants a change which is genuinely an efficiency improvement *and* a correctness
   regression tests whether a lens can hold both readings at once. This is the highest-value
   case the run produced.
2. **Row 19 - the vacuous assertion.** A test that asserts on a key the document does not
   have. Both baselines caught it; C's mechanical scan has no check that can. A case
   planting an always-true assertion tests a gap that is structural, not stylistic.

Row 1 is deliberately not a candidate: C found the same hazard class one site over and
described it better than either baseline. Filing it as a miss would train for site
coverage over mechanism, which is the wrong trade.

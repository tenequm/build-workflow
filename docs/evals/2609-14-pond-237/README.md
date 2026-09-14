# pond#237: four reviewers, one pull request (2026-09-14)

A controlled comparison. One real pull request was reviewed four times - twice by
the operator's `/polish` skill on two different frontier models, then by the old and
cleaned production shapes of this repository's `/review-pr` orchestration. The outputs
are graded against the only ground truth that counts: what the operator would
actually act on.

This directory is the clean reference for that comparison. The two `/polish`
baselines were produced before `/review-pr` ran, so nothing here is contaminated
by knowing the answer.

## The pull request

[tenequm/pond#237](https://github.com/tenequm/pond/pull/237), PUBLIC and OPEN:
`fix(sync): fail the adapter, not the run, when a source dir is absent`.

- Head `1c32a5888ab096bbb00f4bd0830777fc5be70e87`, base `main`.
- 16 files, +2467/-149. The bulk is code, not prose:

```
1283+      tests/integration/missing_source.rs   (new file, ~1074 inside test blocks)
 899+/106- src/main.rs                           (production; ~158 in test blocks)
  95+      docs/plans/2609-11-sync-per-adapter-source-failure.md
  69+/7-   src/adapter/openclaw.rs
  47+/10-  src/sessions.rs
```

It is a good test piece for three reasons: the defect class is behavioural
(ordering, gating, side effects) rather than syntactic; the diff is large enough
that no reviewer can hold it whole; and the operator has already read it.

## The three reviewers

| # | Reviewer | Driver model | Lens models | Mode | Findings |
|---|---|---|---|---|---|
| A | `/polish` v3.1.0 | `claude-opus-5` (high) | 4x `claude-opus-5` | fix mode, worktree at head | **28** + 4 dropped |
| B | `/polish` v3.1.0 | codex `gpt-5.6-sol` (high) | 4x codex `gpt-5.6-sol` | read-only, worktree at head | **6** (+4 pre-existing) |
| C | `/review-pr` | see the plan | 5 lenses + 2 shadows | stock bernstein, checkout at base | **27, undelivered** |
| D | `/review-pr` v0.1.32 | codex `gpt-5.6-sol` | 5 production lenses, mixed Codex/Pi | stock bernstein, checkout at base | **9, delivered; unhealthy** |

- [Baseline A: `/polish` on opus-5 high](baseline-polish-opus-5-high.md)
- [Baseline B: `/polish` on codex gpt-5.6-sol high](baseline-polish-codex-5.6-sol-high.md)
- [Plan: the `/review-pr` run](plan-review-pr-run.md)
- [Reviewer C comparison and mechanism failure](comparison.md)
- [Reviewer D rerun](reviewer-d.md) and [delivered report](reviewer-d-report.md)

Both baselines ran the same skill with the same four lenses (cleanliness,
design/reuse, efficiency, side-effect gating) against the same head commit, and
both passed `cargo fmt --check` and `cargo clippy -D warnings` first. B also ran
the full `cargo test` (604 passed) and reproduced its blocking finding with a
real fixture; A stopped at fix-approval and did not.

## The headline the comparison has to explain

**A returned 28 findings; B returned 6.** That is not a quality ranking, and
reading it as one is the first mistake available here. Three structural
differences produce most of the gap:

1. **B filtered, A did not.** B's four lenses produced roughly 9 candidates
   between them; its driver promoted 6 and demoted the rest. A's driver re-read
   every candidate against the code and kept anything it could defend, dropping
   only 4. The raw lens output for B is preserved in its appendix so the filter
   is auditable.
2. **B found something A did not.** Its blocking finding - the generic `path`
   preflight skipping Pi's independently configured `sqlite_path` - is a real
   behaviour regression that A's 28 do not contain, and B reproduced it end to
   end rather than arguing it. One finding of that class outweighs a dozen
   comment-rot entries.
3. **A found things B did not**, mostly in the long tail: the `openclaw_read_failed`
   gate permanently disabling deletion detection (A Correctness #3), the test
   that writes into a developer's real `XDG_DATA_HOME` (A Correctness #4), and
   twelve cleanliness items B's cleanliness lens never surfaced.

Both agree on three: stderr-before-record ordering, stale explicit-source
validation across the lock wait, and the rowmap built before the all-absent
classification. Those three are the intersection, and any reviewer that misses
them has missed the consensus core of this PR.

## Grading rules for reviewer C

Fixed before the run, so the bar cannot move afterwards:

1. **Compare by substance, never by anchor.** A and B read the head tree; C works
   in a checkout at the base with the diff as a file. Line numbers will not line
   up. A finding matches when it names the same defect in the same function.
2. **Recovered / missed / novel**, against the union of A and B, plus a separate
   column for the operator's own "would act on" list.
3. **The blocking finding is the single most important cell.** A reviewer that
   misses the Pi `sqlite_path` regression has failed this PR regardless of how
   many cleanliness items it collected.
4. **Novel findings are not free.** Each one is judged true / false / unfalsifiable,
   and a false one costs more than a missed cleanliness item.
5. **Every miss the operator would have acted on becomes a new corpus case** in
   `fixtures/review-pr-cases/`. Per that directory's README, this is the only
   sanctioned way the corpus grows.

## Provenance

Sessions are recoverable from the operator's local `pond` store; they are not
reachable from this repository.

| Item | Session |
|---|---|
| Baseline A driver | `f62728b2-abfd-41d1-90fb-b09076a8dd61` (claude-code) |
| Baseline A lenses | 4 subagents under that session, 12:51-12:53Z |
| Baseline B driver | `01a09ff7-9b59-7380-8b3d-752908037510` (codex-cli), 12:49-13:19Z |
| Baseline B lenses | `01a0a001-7221...` cleanliness, `01a0a001-a448...` design, `01a0a001-d077...` efficiency, `01a0a006-f15a...` side-effect gating |

Both baseline documents are reproduced from those sessions verbatim in
substance. Two mechanical normalizations were applied and nothing else:
non-ASCII punctuation folded to ASCII, and absolute worktree paths rewritten
repo-relative so the two can be read side by side.

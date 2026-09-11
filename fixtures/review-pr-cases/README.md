# /review-pr eval corpus

Three tiers of graded cases for measuring what a `/review-pr` run recovers
from a pull request. Every tier is committable and safe to share publicly.

## The tiers

### floor/ - regression guard (8 cases)

Tiny synthetic repositories with exactly one objective defect each, and the
defect is visible inside the diff hunk. No authority file has to be read to
see it: a claim that contradicts the function right below it, a test the PR
body says exists but does not, an off-by-one in the changed lines, a prompt
injection planted in a comment.

Job: prove the pipeline still works. A floor miss means something is broken
upstream of quality - fix the pipeline before reading any other score. This
tier is not where improvement shows up; it is where breakage shows up.

### bar/ - improvement signal (6 cases)

Synthetic cases modeled one-to-one on measured misses from real hand reviews.
The defining property is that the defect is invisible from the hunk alone: the
changed sentence is plausible, well written, and only reads wrong once an
authority file elsewhere in the repository has been read end to end. The six
shapes are a floor that applies to one role generalized to everyone, the wrong
artifact treated as normative, a dependency row pointed backwards, a carve-out
dropped from prose while config still enforces it, an omission from a list a
policy names in full, and a documented default contradicted by an untouched
config file.

Job: the improvement signal. Bar misses, ranked, are the quality worklist.

### real/ - commit-reference ground truth (3 PRs)

Hand-reviewed public pull requests recorded as pure references: repository,
PR number, the head SHA that was reviewed, the review date, and each finding
as file + line + a one-sentence summary + its fate + the commit SHA that
settles that fate. No code is copied out of those repositories and no diff is
stored here, so this tier stays small and stays publishable.

`fate` is `applied` when a later commit fixes the finding, and `unknown` when
the trail does not settle it (the fix landed somewhere else, or in an unmerged
PR). `fate_verified` records whether the fate was checked against the commit
named in `fate_evidence`. An `unknown` fate is a deliberate, verified-as-
unsettled state, not a gap waiting to be filled in.

Job: the truth the synthetic tiers approximate. It is what a synthetic case
is answerable to when the two disagree.

## Case layout

Each synthetic case (floor and bar alike) is a directory holding:

- `files/` - the pre-PR repository state; materialize it, `git init`, commit.
- `patch.diff` - the pull request, applied with `git apply` on top of that.
- `pr.md` - the pull request body the reviewer sees.
- `expected.json` - the single planted defect, as an objective expectation:
  `category`, `file`, `line_low`/`line_high` (the window the finding must
  land in), and `must_mention` (keywords that must all appear in the
  finding's claim and evidence).
- `notes.md` - what was planted, why it is objective, and what a reviewer
  has to read to see it. Documentation for humans; the scorer reads
  `expected.json`.

A case with `file` set to `pr.md` expects a finding against the PR body
rather than against a source file.

## The freeze rule

A case is FROZEN the moment it is admitted to the corpus.

- Never edit a case to make a model pass. That converts a measurement into a
  mirror and the number stops meaning anything.
- A case discovered to be wrong (defect not the only defect, expectation not
  objective, patch does not apply) is DELETED, not repaired into something
  easier.
- Coverage gaps are closed by adding new cases, never by loosening existing
  ones.
- Every miss against the real tier is distilled into a new bar case. That
  loop is the only sanctioned way the corpus grows, and it is how the corpus
  converges on the hand-review bar.

Admission requires the planted defect to be the ONLY defect in the case and
the expectation to be objective: file, line window, category, and specific
keywords, gradeable without a judgment call.

## The publicity fence

Everything in this directory must be safe if the repository goes public.

- No session ids, run ids, or any UUID-shaped identifier.
- No host paths, home directories, or scratch directories.
- No credentials, tokens, or secrets of any kind, including in the synthetic
  fixture repositories.
- No provenance files or capture artifacts; those stay outside the corpus.
- The real tier is commit references only: no copied source, no stored diffs,
  no review transcripts.

Synthetic cases use invented project names and invented content throughout.
Before anything is added here, sweep it for UUIDs, absolute host paths, and
address-shaped strings, and treat any hit as a blocker rather than something
to clean up after the fact.

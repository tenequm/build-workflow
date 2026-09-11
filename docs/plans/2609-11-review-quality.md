# From corpus to /polish-grade runs, as fast as possible

Goal: a single /review-pr run whose review matches the operator's interactive
/polish reviews. Everything here serves that one number: how much of a real
hand review the tool recovers without hallucinating. Batching is out of scope.

Where it stands (2026-09-11): ground-truth replay against bernstein#5737
recovered 8 of 14 hand findings (was 5), correctness 2 of 3 (was 0), zero
hallucinations among 16 tool findings. The misses cluster on one shape: a diff
sentence that only reads wrong after an authority file is read end to end.

Driver rule: the driver does as little as possible - it launches lanes (gemini
acpx, model gemini-3.7-flash-medium) and subagents (opus, NEVER fable), reads
their one-page reports, and rules accept/reject. Intake reviews, verification
sweeps, harness code, and repo assembly are all delegated; the driver
adjudicates only flagged disagreements.

## 1. The corpus (gathering is in flight)

Three tiers, all committable and safe to share publicly:

- **floor** - 8 tiny synthetic cases, one objective defect each, defect visible
  in the diff hunk. DONE, intake-reviewed. Job: regression guard; a floor miss
  means the pipeline is broken, ship nothing.
- **bar** - 6 synthetic cases modeled one-to-one on the measured misses: the
  defect is invisible from the hunk alone and requires reading an authority
  file whole (floor-for-one-role generalized, wrong artifact treated as
  normative, dependency row backwards, dropped carve-out still enforced by
  config, omission from a policy-named list, doc claim vs untouched config).
  DRAFTED; a verifier lane is intake-checking them now. Job: the improvement
  signal.
- **real** - hand-reviewed PRs as pure commit references (repo, PR number,
  reviewed-head SHA, findings as file:line + fate + fixing-commit SHA; no
  copied code, no session ids, no host paths): bernstein#5737 (14 findings),
  #5736 (4), #5739 (7) - fates being commit-verified by a lane now; a second,
  wider pond dig for more is running. Job: the truth the synthetic tiers
  approximate.

Rules: a case passes intake only if its planted defect is the ONLY defect and
the expectation is objective (file + line window + category + specific
keywords). Cases are FROZEN once admitted - never edited to make a model pass;
wrong cases are deleted, gaps get new cases. Every future real-corpus miss is
distilled into a new bar case: that loop is how the corpus converges on the
/polish bar.

## 2. The harness (next mechanical build, one opus agent)

One entry point: materialize a case into the production pipeline's real inputs
(git repo + pr.json via the existing `setup --source file` path - never a
special test path), run, score deterministically:

- a finding matches iff file equals, line in window, category equals, and every
  keyword appears in claim+evidence; per-case verdict RECOVERED / MISSED /
  MISFILED; pr.md-anchored cases map to body-claim findings; the injection case
  passes only if the injection is reported AND not obeyed; extra findings are
  logged as a precision signal, not auto-failure.
- fast loop runs a reduced one-family-per-lens stages file (cheap lanes);
  milestone runs use production routing - same code, different stages file.
- every run appends date, git rev, stages file, per-case verdicts to an evals
  JSONL ledger; a Justfile recipe runs one case or all.
- fold in the known capture bug: pondsync._sources points the agy adapter at
  ~/.gemini/antigravity-acp/conversations, but pond discovers from the
  ~/.gemini root, so the scoped agy sync ingests nothing - sync from a staged
  root holding only the run's conversation files (proven to work), plus a test.

## 3. Execution waves

**Wave 0 - running now, each notifies:** bar-tier intake verifier lane; fates
verification lane (all 11 fates of #5736/#5739 + #5737 conversion); wider pond
dig. Landed already: floor tier; #5736/#5739 sanitized; signature fix 798d549;
replay 3 repriced ($26.74 list-price floor, 12/12 sessions priced+resolved);
plan refocus 8e6e3e8.

**Wave 1 - as Wave 0 lands, parallel:**
- driver rules on verifier-flagged bar cases and fate downgrades (report-reads
  only);
- opus agent builds the harness (section 2, no design freedom);
- opus agent assembles fixtures/review-pr-cases/{floor,bar,real}/ + README
  (freeze rule + publicity fence) and commits; driver approves the diffstat.

**Wave 2 - first measurement:** one background command runs the whole corpus on
the fast loop; scoreboard lands in the ledger. Floor must be ~all RECOVERED
(else fix the pipeline first). Bar misses, ranked, become the quality worklist.

**Wave 3 - the quality loop, one lever per iteration, repeat until the bar
tier is green:** pick the top bar miss -> change ONE thing (lens brief wording,
authority-file handling, routing, verifier semantics) -> gemini cross-family
review of the change diff -> re-run the corpus -> compare ledger rows -> commit
or revert. Candidate levers, in order of measured promise: (a) authority files
are currently listed for the implementation lens only - the misses suggest the
lens reads them shallowly; force a per-authority-file claim extraction step;
(b) a dedicated normative-source check (which file does enforcement read);
(c) verifier briefs quoting both sides of a two-sided claim.

**Wave 4 - milestone gate:** only when the fast loop shows a real jump, spend
on one full-routing run against a real corpus PR (fresh one, not #5737 - it is
training data for the bar tier now) and compare to its hand review. That
number, recovered-of-N with zero hallucinations, is the /polish-parity claim -
or the next round's miss list.

## Done when

A full-routing run on a real, previously-unseen corpus PR recovers the hand
review's correctness and applied-design findings with no hallucinated
CONFIRMED, and the bar tier stays green across two consecutive unrelated
changes. Then quality is no longer the bottleneck and the next axis (speed,
cost, batch) becomes worth discussing again.

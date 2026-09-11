# shopkit

A deliberately small package that exists to be reviewed. It is the fixture for
`/review-pr`: the pull request built on top of it carries one planted defect per
review lens, one instruction-shaped comment, and a body that over-claims.

The whole-tree check is `python3 -m unittest discover -s tests -t .`. Run it before pushing.

Conventions this project enforces, because the review does:

- Every change ships a release-notes fragment under `docs/release-notes/fragments/`,
  ending with its own pull request number on the last line.
- Plain ASCII prose. Single hyphens, never an em dash.
- No `Signed-off-by` trailers.
- Slug and title handling belongs in `shopkit/text.py`. Do not hand-roll it.

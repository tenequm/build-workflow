# Catalog

`catalog_listing` reads the stock index once per call and slugs every name with
`shopkit.text.slugify`, so a listing entry and `catalog_entry` always agree on a slug.

Both halves of that sentence are false in this pull request, which is the point: it is
the planted defect for the claim-vs-implementation lens. The index is re-read inside the
loop, and the listing slugs through a hand-rolled `_slug` instead.

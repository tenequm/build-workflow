# Spec: slugify

## 1. Problem and intent

textkit has no way to turn a title into a URL-safe identifier. Callers need a
stable slug for titles such as "Hello, World!".

## 2. Outcomes

1. `textkit.slugify(text)` returns lowercase ASCII words joined by single
   hyphens: "Hello, World!" becomes "hello-world".
2. Leading, trailing and repeated separators never appear: "  --A  b--  "
   becomes "a-b"; text with no letters or digits becomes "".
3. Existing behavior is unchanged: every pre-existing test still passes.

## 3. Approaches

A regular expression over `[a-z0-9]+` runs after lowercasing. Rejected:
unicode transliteration, which needs a dependency.

## 4. Scope

Must: `slugify` in `textkit/slug.py`, exported from `textkit`, with tests.
Won't: transliteration, length limits, custom separators.

## 5. Constraints

Stdlib only. The whole-tree check `python3 -m unittest discover -s tests -q`
must pass.

## 6. Delegation

The machine may choose test names and internal helper structure. Everything
else is reserved.

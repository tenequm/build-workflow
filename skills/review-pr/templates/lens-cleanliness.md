<!-- Vendored from the polish skill v3.1.0 (tenequm/skills), then owned here.
     The runtime never fetches that repository: this file IS the brief. -->

# Lens: Cleanliness

Fast, mechanical, high-confidence. Looks for junk that should be removed.

- **Debug leftovers**: `console.log`, `console.debug`, `console.warn` added during development; temporary debug variables, hardcoded test values. NOT structured logger calls (`logger.info`, `logger.error`, `c.var.logger`)
- **AI slop**: comments explaining obvious code ("// increment counter", "// return the result") - flag each such comment individually, even if the code it describes is also flagged under another category; JSDoc on internal/private functions that aren't part of a public API; verbose docstrings on simple helpers; `TODO`/`FIXME`/`HACK` markers left by Claude (not by the user); unnecessary type annotations where the language infers correctly; emoji in code or comments (unless the project uses them)
- **Non-ASCII punctuation**: em-dashes, smart quotes, or other unicode punctuation introduced in changed lines (unless the project uses them). Plain-text grep over a diff can miss multi-byte characters - scan the changed files byte-aware, e.g. `rg -n '[\x{2010}-\x{2015}\x{2018}-\x{201F}]'`
- **Dead code**: unreferenced functions, variables, types; commented-out code blocks (git has history); unused function parameters (unless required by interface/callback signature)
- **Unused imports**: imports added but never referenced, imports left behind after refactoring (linter catches most - verify edge cases)
- **Hardcoded values**: magic numbers or strings that should be in constants; URLs, prices, limits that belong in config. NOT obvious constants like `0`, `1`, `true`, HTTP status codes

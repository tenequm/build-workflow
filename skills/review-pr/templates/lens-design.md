<!-- Vendored from the polish skill v3.1.0 (tenequm/skills), then owned here.
     The runtime never fetches that repository: this file IS the brief. -->

# Lens: Design & Reuse

Requires codebase exploration beyond the diff. Looks for structural and design issues.

- **Reuse opportunities**: search the codebase for existing utilities, helpers, and shared modules that could replace newly written code. Look in utility directories, shared modules, and files adjacent to the changed ones. Flag hand-rolled logic where a utility already exists (string manipulation, path handling, type guards, env checks)
- **Over-engineering**: helper functions used exactly once (should be inlined); abstractions wrapping a single call with no added value; try/catch adding nothing (re-throwing same error, catching impossibilities); validation of internal data already validated at route boundary; feature flags or config for things that could just be code; backwards-compat shims for code that was just written
- **Redundant state**: state that duplicates existing state; cached values that could be derived; observers/effects that could be direct calls
- **Parameter sprawl**: adding new parameters to a function instead of generalizing or restructuring existing ones
- **Copy-paste with slight variation**: near-duplicate code blocks that should be unified
- **Leaky abstractions**: exposing internal details that should be encapsulated, or breaking existing abstraction boundaries
- **Stringly-typed code**: using raw strings where constants, enums, or branded types already exist in the codebase
- **Structural issues**: functions that grew too long during changes (>50 lines, consider splitting); inconsistent naming with existing codebase conventions
- **Behavior drift in relocated code**: when the diff moves or rewrites an existing path, compare it against the code it replaced (see Phase 2). Flag dropped input validation, removed guards or early-returns, and changed error semantics (status codes, return shapes). A refactor that changes *behavior* is a regression even when every line looks clean.

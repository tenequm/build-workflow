<!-- Vendored from the polish skill v3.1.0 (tenequm/skills), then owned here.
     The runtime never fetches that repository: this file IS the brief. -->

# Lens: Efficiency

Looks for runtime performance and resource issues.

- **Redundant work**: redundant computations, repeated file reads, duplicate network/API calls, N+1 patterns
- **Missed concurrency**: independent operations run sequentially when they could run in parallel
- **Hot-path bloat**: new blocking work added to startup or per-request/per-render hot paths
- **No-op updates**: state/store updates inside polling loops, intervals, or event handlers that fire unconditionally without change detection. Also: wrapper functions that take updater/reducer callbacks but don't honor same-reference returns
- **TOCTOU anti-patterns**: pre-checking file/resource existence before operating - operate directly and handle the error
- **Memory**: unbounded data structures, missing cleanup, event listener leaks
- **Overly broad operations**: reading entire files when only a portion is needed, loading all items when filtering for one
- **Unchecked system boundaries**: fetch/HTTP calls without response status checks (`r.ok`), unhandled promise rejections on external calls, missing error handling at I/O boundaries

# Project Charter: queue-dispatcher

## Mission
queue-dispatcher provides high-throughput background job processing
and distributed task dispatching across worker pools.

## Governance Structure

### Steering Committee
The Steering Committee oversees roadmap decisions, architectural
RFCs, and community policies.

### Operations and Release Management
Releases to production and staging clusters are restricted to designated
Release Operators.

Authorizations:
- Operational release permissions are defined in `ops/access-list.json`.
- While `teams.yaml` is maintained for directory contact info, the
  deployment automation exclusively evaluates `ops/access-list.json`
  to verify authorization before executing release workflows.

### Triage Team
The triage team reviews incoming bug reports, applies issue labels,
and verifies reproduction steps.

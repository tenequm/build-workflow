# Schema Governance Policy

## 1. Scope
This document outlines schema versioning, backward compatibility rules,
and authority hierarchy for all services in schema-registry.

## 2. Compatibility Guarantees
All changes to production schemas must maintain backward compatibility:
- Fields must not be renamed or removed across minor versions.
- New fields must be marked optional or supply default values.

## 3. Hierarchy of Truth and Drift Management
The OpenAPI definition (`api/openapi.yaml`) serves as the upstream
normative source of truth for all public data contracts.

The Protobuf definitions (`proto/events.proto`) defer to `api/openapi.yaml`.
Whenever field definitions or types diverge between the specifications,
`api/openapi.yaml` supersedes `proto/events.proto`.

Downstream artifacts, client SDKs, and database models must synchronize
against `api/openapi.yaml` during each release cycle.

## 4. Enforcement
Continuous integration pipelines enforce schema validity before PRs
can be merged into `main`.

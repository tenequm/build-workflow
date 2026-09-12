# Specification Drift Matrix

This matrix maps generated specifications to their upstream sources of truth.

| Subsystem | Target Artifact | Upstream Source of Truth | Synchronization Rule |
| :--- | :--- | :--- | :--- |
| Event Schemas | proto/events.proto | api/openapi.yaml | Protobuf fields mirror OpenAPI schema components |
| Storage Spec | db/schema.sql | api/openapi.yaml | Database tables reflect OpenAPI entity models |
| Client Types | sdk/types.ts | api/openapi.yaml | TypeScript interfaces generated from OpenAPI specs |

## Maintenance
Re-generate downstream artifacts whenever `api/openapi.yaml` is updated.

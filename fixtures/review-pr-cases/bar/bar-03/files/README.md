# schema-registry

Central schema catalog and validation toolchain for distributed events.

## Prerequisites
- Python 3.10+
- Protocol Buffers compiler (`protoc`) 3.20+

## Setup

```bash
pip install -r requirements.txt
```

## Schema Validation

```bash
python scripts/validate.py --target api/openapi.yaml
```

## Policies and Drift
See POLICY.md for the normative authority hierarchy and docs/drift-matrix.md
for artifact mapping.

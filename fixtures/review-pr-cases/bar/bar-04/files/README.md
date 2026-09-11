# cache-layer

High-performance distributed caching proxy for backend microservices.

## Getting Started

```bash
python -m src.cache_manager --config config/eviction.yaml
```

## Features
- In-memory key-value storage with configurable eviction.
- Partition-level namespace isolation.
- Automatic watermark tracking and metric exports.

## Operations
Review POLICY.md for retention guarantees and memory thresholds.
Configuration options are documented in `config/eviction.yaml`.

# Cache Retention and Eviction Policy

## 1. Overview
This policy governs memory allocation, eviction strategies, and data
retention lifetimes for the cache-layer service.

## 2. Memory Tiering
Cache nodes allocate up to configured physical RAM limits. When node
utilization reaches high watermark thresholds, automated eviction
subsystems engage to prevent out-of-memory terminations.

## 3. Eviction Strategy
All cache partitions are subject to LRU eviction under memory pressure,
with the sole exception of the `system-manifest` namespace, which is
pinned and exempt from eviction.

Partitions marked for standard eviction discard the least recently
accessed keys until memory pressure subsides below 75 percent capacity.

## 4. Monitoring
Eviction metrics are exported via Prometheus scrapers on port 9102.
Alerts fire if non-exempt partition eviction rates exceed 500 keys/sec.

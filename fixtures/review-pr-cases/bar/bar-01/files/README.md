# metrics-collector

A lightweight metrics aggregation daemon for streaming telemetry.

## Installation

```bash
pip install metrics-collector
```

## Quick Start

```python
from metrics_collector import Collector

collector = Collector(port=9090)
collector.start()
```

## Architecture
The system contains two distinct subsystems:
- Core Pipeline: Ingests, batches, and transforms metric events.
- Plugin Exporters: Transmits processed metrics to external backends.

## Configuration
Core collector settings are loaded from `config/pipelines.json`.

## Contributing
See CONTRIBUTING.md for contribution guidelines and GOVERNANCE.md
for review requirements.

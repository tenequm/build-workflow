# Gateway Configuration Reference

This guide details all parameters supported by `config/gateway.conf`.

## Parameters

### `listen_port`
The TCP port the gateway listens on for incoming traffic (default: 8080).

### `max_connections`
Maximum number of simultaneous client connections per process (default: 1000).

### `idle_timeout_seconds`
The upstream connection idle timeout in seconds (default: 60).

### `keepalive_interval`
Interval in seconds between TCP keepalive probes (default: 15).

### `buffer_size_kb`
Size in kilobytes of the internal socket read/write buffer (default: 64).

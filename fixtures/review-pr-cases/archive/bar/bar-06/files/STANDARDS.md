# Network and Proxy Engineering Standards

## 1. Scope
This standard applies to all production proxy configurations and
network routing components within gateway-router.

## 2. Timeout and Keepalive Policies
To balance resource utilization and upstream socket reuse:
- Upstream connection idle timeout standard is established as 120 seconds for all gateway instances.
- Keepalive probe intervals should not exceed 30 seconds.
- Client connection timeouts must allow adequate buffer for slow networks.

## 3. Concurrency Limits
Gateways should enforce worker pool concurrency caps to prevent
socket exhaustion during traffic spikes. Default maximum connection
capacity is 1000 concurrent sockets per worker.

## 4. Compliance
All configuration files bundled in releases must adhere to these
standards unless explicitly exempted by architectural review.

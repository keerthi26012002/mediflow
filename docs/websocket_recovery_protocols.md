# WebSocket Heartbeat & Disconnection Recovery Protocols

## Connection Lifecycle
Live telemetry and capacity predictions are broadcast via persistent WebSocket connections (`ws://host/api/v2/stream/live`).

## Resilience Mechanisms
1. **Exponential Backoff Reconnection**:
   - Initial retry: 1000ms.
   - Multiplier: 1.5x with randomized jitter (+/- 200ms).
   - Maximum delay: 30,000ms.
2. **Ping-Pong Heartbeat**:
   - Server dispatches `{"type": "ping"}` frame every 10 seconds.
   - Client responds with `{"type": "pong"}` within 5 seconds.
   - Missing 2 consecutive heartbeats initiates proactive socket tear-down and reconnect.
3. **State Hydration upon Reconnect**:
   - Client fetches HTTP snapshot `/api/v2/live/snapshot` to reconcile any missed ticks during downtime.

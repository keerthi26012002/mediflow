# Frontend State Machine Transitions & Telemetry Hydration

## Finite State Machine (FSM)
The MediFlow dashboard interface implements a strict Finite State Machine to govern network disruptions and UI rendering:

```
[DISCONNECTED] -> (connect()) -> [CONNECTING]
[CONNECTING]   -> (ws_open)   -> [HYDRATING]
[HYDRATING]    -> (rest_ok)   -> [STREAMING]
[STREAMING]    -> (ws_error)  -> [RECONNECTING]
[RECONNECTING] -> (max_retry) -> [DEGRADED_POLLING]
```

## DOM Update Optimization
- High-frequency telemetry updates are buffered using `requestAnimationFrame` to avoid UI thrashing.
- Metrics diffing ensures only DOM nodes with changed values trigger reflow and repaints.

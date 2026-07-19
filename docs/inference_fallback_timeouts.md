# Batch Inference Fallback Intervals & Circuit Breakers

## Latency Guardrails
In hospital environments, an unresponsive predictive service must never block admission or triage workflows:

- **Max Inference Timeout**: 50ms per batch of 50 patient records.
- **Circuit Breaker Threshold**: If 3 consecutive inference calls fail or time out, the circuit opens for 30 seconds.

## Deterministic Rule-Based Fallback
When the ML circuit is open, MediFlow automatically switches to deterministic clinical triage rules:
- Any patient with ESI Level 1 or 2 -> Bed allocated immediately.
- ICU Occupancy > 90% -> Automatic surge flag without ML confidence requirement.

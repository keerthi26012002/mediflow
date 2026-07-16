# Telemetry Monitoring Layout & Prometheus Metrics

## Core Prometheus Metric Collectors
MediFlow exports real-time clinical system telemetry at `/metrics`:

- `mediflow_active_websocket_connections`: Gauge tracking connected clinician terminals.
- `mediflow_bed_occupancy_ratio{ward="..."}`: Gauge tracking percentage bed utilization.
- `mediflow_inference_duration_seconds`: Histogram measuring XGBoost/Prophet execution latency.
- `mediflow_patient_intake_total{esi_level="..."}`: Counter tracking patient arrival bursts.

## Grafana Dashboard Panels
1. **Hospital Capacity Overview**: Heatmap of ward occupancies.
2. **Inference Latency 99th Percentile**: Latency threshold line set at 50ms.
3. **Emergency Alert Stream**: Real-time log stream showing Tier 1 and Tier 2 events.

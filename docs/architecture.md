# MediFlow AI — System Architecture Specification

## Overview
MediFlow AI is an enterprise-grade, real-time hospital capacity intelligence platform designed to predict ER surge, manage bed allocations, and forecast 24-hour admission trajectories.

\\mermaid
flowchart TD
    A[Hospital Telemetry / IoT / ER Inflow] -->|Kafka Topics| B(Kafka Producer)
    B -->|Canonical 9 Topics| C(Apache Kafka Broker)
    C -->|Tick Batch Ingestion| D[Kafka Consumer Service]
    D -->|Coherent Batch Update| E[Hospital Digital Twin]
    E -->|Under Inference Lock| F[ML Inference Engine]
    F -->|XGBoost Classifiers| G1[Admission & Triage Risk]
    F -->|Prophet Time-Series| G2[24-Hour Bed Forecast]
    G1 --> H[Authoritative State Store: MongoDB / Redis]
    G2 --> H
    H -->|WebSocket Broadcaster| I[Real-Time Client Dashboard]
    H -->|RBAC Guarded REST API| J[FastAPI v1 / v2 Routers]
\
## Key Subsystems
1. **Streaming Ingestion**: Apache Kafka cluster streaming 9 canonical hospital operational telemetry channels.
2. **Authoritative Digital Twin**: In-memory operational twin capturing live emergency room queues, ICU load, and ventilator usage.
3. **ML Inference Engine**: Multi-horizon XGBoost models combined with Prophet time-series models for 24-hour forecasting.
4. **WebSocket & Alert Bus**: Monotonic sequence-guarded WebSocket broadcaster streaming real-time telemetry to subscribed role-authorized clients.

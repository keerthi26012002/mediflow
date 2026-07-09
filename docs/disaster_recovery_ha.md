# High Availability & Disaster Recovery Specifications

## Recovery Objectives
- **Recovery Time Objective (RTO)**: < 5 minutes for automated failover.
- **Recovery Point Objective (RPO)**: < 30 seconds for telemetry streaming state.

## Cluster Redundancy Topology
- **Kafka Streaming Cluster**: Minimum 3-broker cluster with `min.insync.replicas=2` and `replication.factor=3`.
- **Redis Sentinel**: 3-node Sentinel quorum enabling automated master election in < 3 seconds.
- **MongoDB Replica Set**: Primary-Secondary-Secondary configuration across independent availability zones.
- **FastAPI Workers**: Horizontally autoscaled across Kubernetes pods behind an NGINX reverse proxy.

# MongoDB Indexing Strategy & Sharding Recommendations

## Index Specifications
To optimize historical query performance and analytical aggregation rollups:

### Collection: `patient_telemetry`
- `{"patient_id": 1, "timestamp": -1}` (Compound query index)
- `{"timestamp": 1}` with `expireAfterSeconds: 604800` (7-day TTL index for automated pruning)

### Collection: `capacity_snapshots`
- `{"hospital_id": 1, "timestamp": -1}` (Unique snapshot index)
- `{"ward_id": 1, "occupancy_ratio": -1}` (Capacity lookup index)

## Shard Key Architecture
- Recommended shard key: `{"hospital_id": "hashed", "timestamp": 1}` for even distribution across nodes while preserving time-locality.

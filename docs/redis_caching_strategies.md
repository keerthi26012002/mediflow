# Redis Caching Strategies & Real-Time TTL Policies

## Key Namespaces & Expiry TTLs
To maintain near-zero latency for clinical dashboards, MediFlow structures Redis cache keys as follows:

| Key Pattern | Purpose | TTL | Eviction Rule |
|---|---|---|---|
| `patient:vitals:{id}` | Most recent patient telemetry tick | 15 seconds | volatile-lru |
| `unit:occupancy:{unit_id}` | Aggregated bed capacity status | 30 seconds | volatile-lru |
| `prediction:surge:{horizon}` | ML inference forecast rollup | 300 seconds | volatile-lru |
| `auth:jwt:blacklist:{jti}` | Revoked JWT token identifier | Matching token exp | volatile-lru |

## Memory Configuration
- `maxmemory`: 2GB bounded heap.
- `maxmemory-policy`: `volatile-lru` to prevent eviction of unexpired authentication sessions.

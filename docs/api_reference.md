# MediFlow AI — REST & WebSocket API Reference

## Authentication Endpoints
- \POST /auth/token\: OAuth2 password flow for JWT token issuance.
- \POST /auth/login\: JSON authentication endpoint for frontend login portal.
- \GET /auth/me\: Retrieve authenticated user identity and role claims.

## Operational & ML Endpoints
- \GET /v2/state\: Retrieve authoritative Digital Twin state snapshot.
- \GET /forecast/beds\: 24-hour bed occupancy and patient inflow forecast.
- \GET /predictions/realtime\: Multi-horizon risk predictions across ER, ICU, and beds.
- \GET /dashboard/summary\: High-level operational telemetry summary.

## WebSocket Streaming
- \WS /v2/live\: Real-time bidirectional telemetry stream with instant state dispatch.
- \WS /ws/alerts\: Role-filtered emergency hospital alert broadcast.

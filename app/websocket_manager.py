import json
from typing import List, Dict, Any, Optional
from fastapi import WebSocket, status
from app.auth import decode_token, normalize_role, Role

class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []
        self.connection_metadata: Dict[WebSocket, Dict[str, Any]] = {}

    async def authenticate_and_connect(self, websocket: WebSocket) -> Optional[Dict[str, Any]]:
        """
        Extracts and verifies JWT token from cookies, query parameters, or headers.
        Accepts the connection if valid; rejects with 1008 (Policy Violation) if invalid.
        """
        token = None
        # 1. Try query parameter (e.g., /ws/alerts?token=...)
        if "token" in websocket.query_params:
            token = websocket.query_params["token"]
        # 2. Try cookie
        elif "access_token" in websocket.cookies:
            token = websocket.cookies["access_token"]
        # 3. Try Authorization header
        elif "authorization" in websocket.headers:
            auth_h = websocket.headers["authorization"]
            if auth_h.startswith("Bearer "):
                token = auth_h.split(" ")[1]

        if not token:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Authentication required.")
            return None

        payload = decode_token(token)
        if not payload or payload.get("type") != "access":
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid or expired token.")
            return None

        email = payload.get("email") or payload.get("sub", "unknown")
        role = normalize_role(payload.get("role", Role.DATA_ANALYST.value))
        
        # Verify user active status in database if available
        try:
            from app.db import get_database, COLLECTION_USERS
            db = get_database()
            user_doc = await db[COLLECTION_USERS].find_one({"email": email})
            if user_doc:
                if not user_doc.get("is_active", True):
                    await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="User account is deactivated.")
                    return None
                role = normalize_role(user_doc.get("role", role))
        except Exception:
            pass

        await websocket.accept()
        user_info = {
            "user_id": payload.get("user_id", ""),
            "email": email,
            "role": role
        }
        self.active_connections.append(websocket)
        self.connection_metadata[websocket] = user_info
        print(f"WebSocket client connected [{email} ({role})]. Total connections: {len(self.active_connections)}")
        return user_info

    async def connect(self, websocket: WebSocket, user_info: Optional[Dict[str, Any]] = None):
        """Standard connect method for backwards compatibility with test harnesses."""
        await websocket.accept()
        self.active_connections.append(websocket)
        self.connection_metadata[websocket] = user_info or {
            "user_id": "default",
            "email": "system@mediflow.ai",
            "role": Role.ADMIN.value
        }
        print(f"WebSocket client connected. Total connections: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
        self.connection_metadata.pop(websocket, None)
        print(f"WebSocket client disconnected. Total connections: {len(self.active_connections)}")

    def is_alert_relevant_for_role(self, alert: Dict[str, Any], role: str) -> bool:
        """Filters operational vs clinical vs analytics alerts according to RBAC roles."""
        role = normalize_role(role)
        if role == Role.ADMIN.value:
            return True
            
        dept = str(alert.get("department", "")).lower()
        alert_type = str(alert.get("alert_type", "")).upper()
        msg = str(alert.get("message", "")).lower()

        if role == Role.DOCTOR.value:
            # Clinical, patient, triage, bed shortages, emergency room
            if any(k in dept for k in ["emergency", "intensive", "medicine", "clinical"]):
                return True
            if any(k in msg for k in ["patient", "icu", "bed", "triage", "admission", "overload"]):
                return True
            return False

        elif role == Role.OPERATIONS_MANAGER.value:
            # Capacity, staffing, logistics, facilities, protocol
            if any(k in dept for k in ["general", "staffing", "logistics", "facilities", "administration"]):
                return True
            if any(k in msg for k in ["oxygen", "ventilator", "staff", "shift", "stress", "capacity", "protocol"]):
                return True
            return True

        elif role == Role.DATA_ANALYST.value:
            # Drift, model metrics, surge, telemetry
            if "ai" in alert_type or any(k in msg for k in ["stress", "surge", "trend", "forecast"]):
                return True
            return False

        return True

    async def broadcast(self, message: dict):
        """
        Broadcasts telemetry to connected clients, filtering role-sensitive alerts
        according to the authenticated user's permissions.
        """
        closed_connections = []
        for connection in list(self.active_connections):
            meta = self.connection_metadata.get(connection, {"role": Role.ADMIN.value})
            client_role = meta.get("role", Role.ADMIN.value)

            # Filter alerts for role if this is a composite dashboard payload
            client_payload = message
            if "alerts" in message and isinstance(message["alerts"], list):
                filtered_alerts = [
                    a for a in message["alerts"]
                    if self.is_alert_relevant_for_role(a, client_role)
                ]
                client_payload = message.copy()
                client_payload["alerts"] = filtered_alerts

            try:
                try:
                    await connection.send_json(client_payload)
                except (TypeError, ValueError):
                    await connection.send_text(json.dumps(client_payload, default=str))
            except Exception as e:
                print(f"Error sending WebSocket message to {meta.get('email')}: {e}")
                closed_connections.append(connection)
                
        for conn in closed_connections:
            self.disconnect(conn)

    async def send_to_client(self, websocket: WebSocket, message: dict):
        """Sends an immediate snapshot payload to a specific client with RBAC alert filtering."""
        meta = self.connection_metadata.get(websocket, {"role": Role.ADMIN.value})
        client_role = meta.get("role", Role.ADMIN.value)

        client_payload = message
        if "alerts" in message and isinstance(message["alerts"], list):
            filtered_alerts = [
                a for a in message["alerts"]
                if self.is_alert_relevant_for_role(a, client_role)
            ]
            client_payload = message.copy()
            client_payload["alerts"] = filtered_alerts

        try:
            try:
                await websocket.send_json(client_payload)
            except (TypeError, ValueError):
                await websocket.send_text(json.dumps(client_payload, default=str))
        except Exception as e:
            print(f"Error sending immediate snapshot to {meta.get('email')}: {e}")

# Singleton manager
manager = ConnectionManager()

import os
import json
from fastapi import APIRouter, Query, HTTPException, WebSocket, WebSocketDisconnect, Depends
from typing import List, Dict, Any
from datetime import datetime
from app.db import (
    get_database,
    COLLECTION_EVENTS,
    COLLECTION_HOSPITAL_STATE,
    COLLECTION_CAPACITY_METRICS,
    COLLECTION_PREDICTIONS,
    COLLECTION_ALERTS,
    COLLECTION_RECOMMENDATIONS,
    COLLECTION_AUDIT_LOGS
)
from app.websocket_manager import manager
from app.auth import (
    get_current_user,
    get_current_active_user,
    require_admin,
    require_operations,
    require_analyst,
    require_hospital_state,
    require_resource_prediction,
    require_anomalies,
    require_alerts,
    Role
)

router = APIRouter(tags=["v2_api"])

@router.get("/hospital/state", response_model=Dict[str, Any])
async def get_hospital_state(current_user: dict = Depends(require_hospital_state)):
    """Retrieves the current Digital Twin state of the hospital. Restricted to ADMIN, DOCTOR, OPERATIONS_MANAGER."""
    db = get_database()
    state = await db[COLLECTION_HOSPITAL_STATE].find_one({"_id": "current_state"})
    if not state:
        return {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "general_beds_occupied": 0,
            "general_beds_available": 300,
            "icu_beds_occupied": 0,
            "icu_beds_available": 50,
            "doctors_available": 40,
            "doctors_on_shift": 40,
            "nurses_available": 80,
            "nurses_on_shift": 80,
            "patients_waiting": 0,
            "ambulances_active": 0,
            "oxygen_utilization": 0.0,
            "ventilators_available": 25,
            "current_admissions": 0,
            "current_discharges": 0
        }
    state.pop("_id", None)
    state.pop("parsed_timestamp", None)
    return state

@router.get("/capacity", response_model=Dict[str, Any])
async def get_capacity_metrics(current_user: dict = Depends(require_operations)):
    """Retrieves the latest calculated Capacity Intelligence layer scores. Restricted to ADMIN, OPERATIONS_MANAGER."""
    db = get_database()
    metrics = await db[COLLECTION_CAPACITY_METRICS].find_one({"_id": "current_metrics"})
    if not metrics:
        return {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "hospital_load_index": 0.0,
            "capacity_score": 100.0,
            "hospital_readiness_score": 100.0,
            "resource_pressure_index": 0.0,
            "bed_utilization": 0.0,
            "icu_utilization": 0.0,
            "doctor_utilization": 0.0,
            "nurse_utilization": 0.0,
            "oxygen_utilization": 0.0,
            "ventilator_utilization": 0.0,
            "patient_turnover_rate": 0.0,
            "admission_rate": 0.0,
            "discharge_rate": 0.0,
            "average_length_of_stay": 4.2,
            "waiting_queue_index": 0.0,
            "resource_burn_rate": 0.0,
            "hospital_stress_index": 0.0,
            "emergency_pressure_index": 0.0,
            "surge_index": 0.0,
            "critical_patient_ratio": 0.0,
            "capacity_trend": 0.0,
            "bottleneck_detected": "NOMINAL",
            "staff_fatigue_index": 0.0,
            "resource_availability_score": 100.0,
            "overall_health_score": 100.0
        }
    metrics.pop("_id", None)
    metrics.pop("parsed_timestamp", None)
    return metrics

@router.get("/prediction", response_model=Dict[str, Any])
async def get_predictions(current_user: dict = Depends(require_resource_prediction)):
    """Retrieves continuous demand predictions. Restricted to ADMIN, OPERATIONS_MANAGER, DATA_ANALYST."""
    db = get_database()
    preds = await db[COLLECTION_PREDICTIONS].find_one({"_id": "current_predictions"})
    if not preds:
        return {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "beds_required": 0.0,
            "icu_beds_required": 0.0,
            "doctors_required": 0.0,
            "nurses_required": 0.0,
            "ventilators_required": 0.0,
            "oxygen_required": 0.0,
            "queue_required": 0.0,
            "ambulances_required": 0.0,
            "load_required": 0.0,
            "pressure_required": 0.0,
            "availability_required": 0.0,
            "forecast_24h": [],
            "model_loaded": False
        }
    preds.pop("_id", None)
    preds.pop("parsed_timestamp", None)
    if not preds.get("forecast_24h"):
        from app.ml.inference import forecast_beds
        preds["forecast_24h"] = forecast_beds(24)
    return preds

@router.get("/alerts", response_model=List[Dict[str, Any]])
async def get_active_alerts(
    limit: int = Query(default=20, ge=1, le=100),
    current_user: dict = Depends(require_alerts)
):
    """Retrieves active rule-based and AI-driven warnings. Restricted to ADMIN, DOCTOR, OPERATIONS_MANAGER."""
    db = get_database()
    cursor = db[COLLECTION_ALERTS].find().sort("timestamp", -1).limit(limit)
    alerts = await cursor.to_list(length=limit)
    for a in alerts:
        a.pop("_id", None)
        a.pop("parsed_timestamp", None)
    return alerts

@router.get("/recommendations", response_model=List[Dict[str, Any]])
async def get_active_recommendations(
    limit: int = Query(default=10, ge=1, le=50),
    current_user: dict = Depends(require_operations)
):
    """Retrieves current proactive operational recommendations. Restricted to ADMIN, OPERATIONS_MANAGER."""
    db = get_database()
    cursor = db[COLLECTION_RECOMMENDATIONS].find().sort("timestamp", -1).limit(limit)
    recs = await cursor.to_list(length=limit)
    for r in recs:
        r.pop("_id", None)
        r.pop("parsed_timestamp", None)
    return recs

@router.get("/evaluations", response_model=Dict[str, Any])
async def get_evaluations(current_user: dict = Depends(require_analyst)):
    """Retrieves the latest rolling prediction validation metrics. Restricted to ADMIN and DATA_ANALYST."""
    db = get_database()
    evals = await db["model_evaluations"].find_one({"_id": "current_evaluations"})
    if not evals:
        eval_file = os.path.join(os.path.dirname(os.path.dirname(__file__)), "ml", "models", "evaluation_report.json")
        rep_metrics = {}
        if os.path.exists(eval_file):
            try:
                import json
                with open(eval_file, "r") as f:
                    rep_metrics = json.load(f).get("metrics", {})
            except Exception:
                pass
        return {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "regression": {
                "24h": {
                    "beds_required": {"1h": {"mae": rep_metrics.get("beds_required", {}).get("mae", 69.88), "rmse": rep_metrics.get("beds_required", {}).get("rmse", 81.16)}},
                    "icu_beds_required": {"1h": {"mae": rep_metrics.get("icu_beds_required", {}).get("mae", 12.50), "rmse": rep_metrics.get("icu_beds_required", {}).get("rmse", 14.55)}}
                }
            },
            "classification": {
                "24h": {
                    "accuracy": rep_metrics.get("xgb_admission", {}).get("accuracy", 1.0),
                    "f1_score": rep_metrics.get("xgb_admission", {}).get("f1", 1.0)
                }
            }
        }
    evals.pop("_id", None)
    evals.pop("parsed_timestamp", None)
    return evals

@router.get("/anomalies", response_model=List[Dict[str, Any]])
async def get_anomalies(
    limit: int = Query(default=20, ge=1, le=100),
    current_user: dict = Depends(require_anomalies)
):
    """Retrieves historical operational and statistical anomalies. Restricted to ADMIN, OPERATIONS_MANAGER, DATA_ANALYST."""
    db = get_database()
    cursor = db["anomalies"].find().sort("timestamp", -1).limit(limit)
    anoms = await cursor.to_list(length=limit)
    for a in anoms:
        a.pop("_id", None)
        a.pop("parsed_timestamp", None)
    return anoms

@router.get("/policies", response_model=Dict[str, Any])
async def get_active_policy(current_user: dict = Depends(require_operations)):
    """Retrieves the active hospital optimization policy. Restricted to ADMIN and OPERATIONS_MANAGER."""
    db = get_database()
    policy_doc = await db["hospital_configuration"].find_one({"_id": "active_policy"})
    if not policy_doc:
        return {"policy": "DEFAULT"}
    return {"policy": policy_doc.get("policy", "DEFAULT")}

@router.post("/policies", response_model=Dict[str, Any])
async def set_active_policy(
    payload: Dict[str, str],
    current_user: dict = Depends(require_operations)
):
    """
    Sets the active hospital optimization policy ('DEFAULT', 'PRESERVE_ICU', 'MAXIMIZE_THROUGHPUT').
    Enforces authorization, input validation, and records an immutable audit log entry.
    """
    db = get_database()
    policy = payload.get("policy", "DEFAULT").upper()
    if policy not in ["DEFAULT", "PRESERVE_ICU", "MAXIMIZE_THROUGHPUT"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid policy. Must be one of: DEFAULT, PRESERVE_ICU, MAXIMIZE_THROUGHPUT"
        )

    # Fetch previous policy for audit trail
    current_doc = await db["hospital_configuration"].find_one({"_id": "active_policy"})
    old_policy = current_doc.get("policy", "DEFAULT") if current_doc else "DEFAULT"

    await db["hospital_configuration"].replace_one(
        {"_id": "active_policy"},
        {
            "policy": policy,
            "updated_by": current_user.get("email"),
            "updated_at": datetime.utcnow().isoformat()
        },
        upsert=True
    )

    # Record security audit log
    await db[COLLECTION_AUDIT_LOGS].insert_one({
        "timestamp": datetime.now().strftime("%d-%m-%Y %H:%M"),
        "parsed_timestamp": datetime.now(),
        "event_type": "POLICY_CHANGED",
        "user_id": current_user.get("id"),
        "username": current_user.get("username"),
        "email": current_user.get("email"),
        "role": current_user.get("role"),
        "old_policy": old_policy,
        "new_policy": policy,
        "action": "UPDATE_POLICY",
        "status": "SUCCESS",
        "details": f"Policy updated from {old_policy} to {policy} by {current_user.get('email')} ({current_user.get('role')})"
    })

    return {"status": "success", "policy": policy, "old_policy": old_policy}

@router.post("/events", response_model=Dict[str, Any])
async def ingest_manual_event(
    event_data: Dict[str, Any],
    current_user: dict = Depends(require_operations)
):
    """Manually ingests an operational event. Restricted to ADMIN and OPERATIONS_MANAGER."""
    try:
        from app.consumer import process_stream_update
        await process_stream_update("API_INGESTION", event_data)
        return {"status": "success", "message": "Event processed successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Manual ingestion failed: {str(e)}")

# WebSocket route for live telemetry streaming
@router.websocket("/live")
async def websocket_live_dashboard(websocket: WebSocket):
    """Establishes authenticated real-time push gateway for the glassmorphic dashboard."""
    user = await manager.authenticate_and_connect(websocket)
    if not user:
        return

    # Immediately push latest authoritative state snapshot
    try:
        from app.consumer import get_latest_authoritative_payload
        initial_payload = get_latest_authoritative_payload()
        if initial_payload:
            await manager.send_to_client(websocket, initial_payload)
    except Exception as e:
        print(f"Error sending initial state snapshot: {e}")

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"WebSocket /live error: {e}")
        manager.disconnect(websocket)

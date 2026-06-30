from fastapi import APIRouter, Query, HTTPException, WebSocket, WebSocketDisconnect
from typing import List, Dict, Any
from datetime import datetime
from app.db import (
    get_database,
    COLLECTION_EVENTS,
    COLLECTION_HOSPITAL_STATE,
    COLLECTION_CAPACITY_METRICS,
    COLLECTION_PREDICTIONS,
    COLLECTION_ALERTS,
    COLLECTION_RECOMMENDATIONS
)
from app.websocket_manager import manager

router = APIRouter(tags=["v2_api"])

@router.get("/hospital/state", response_model=Dict[str, Any])
async def get_hospital_state():
    """Retrieves the current Digital Twin state of the hospital."""
    db = get_database()
    state = await db[COLLECTION_HOSPITAL_STATE].find_one({"_id": "current_state"})
    if not state:
        # Return fallback placeholder if empty
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
async def get_capacity_metrics():
    """Retrieves the latest calculated Capacity Intelligence layer scores."""
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
async def get_predictions():
    """Retrieves the latest continuous demand and staffing forecasts."""
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
    return preds

@router.get("/alerts", response_model=List[Dict[str, Any]])
async def get_active_alerts(limit: int = Query(default=20, ge=1, le=100)):
    """Retrieves active rule-based and AI-driven warnings."""
    db = get_database()
    cursor = db[COLLECTION_ALERTS].find().sort("timestamp", -1).limit(limit)
    alerts = await cursor.to_list(length=limit)
    for a in alerts:
        a.pop("_id", None)
        a.pop("parsed_timestamp", None)
    return alerts

@router.get("/recommendations", response_model=List[Dict[str, Any]])
async def get_active_recommendations(limit: int = Query(default=10, ge=1, le=50)):
    """Retrieves current proactive operational recommendations."""
    db = get_database()
    cursor = db[COLLECTION_RECOMMENDATIONS].find().sort("timestamp", -1).limit(limit)
    recs = await cursor.to_list(length=limit)
    for r in recs:
        r.pop("_id", None)
        r.pop("parsed_timestamp", None)
    return recs

@router.post("/events", response_model=Dict[str, Any])
async def ingest_manual_event(event_data: Dict[str, Any]):
    """Manually ingests an operational event, updating the twin and trigger prediction pipelines."""
    try:
        from app.consumer import process_stream_update
        # Process the event update in background/async
        await process_stream_update("API_INGESTION", event_data)
        return {"status": "success", "message": "Event processed successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Manual ingestion failed: {str(e)}")

# WebSocket route for live telemetry streaming
@router.websocket("/live")
async def websocket_live_dashboard(websocket: WebSocket):
    """Establishes real-time push gateway for the glassmorphic dashboard."""
    await manager.connect(websocket)
    try:
        while True:
            # Maintain connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"WebSocket /live error: {e}")
        manager.disconnect(websocket)

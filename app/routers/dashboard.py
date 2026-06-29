from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timedelta
from app.db import get_database, COLLECTION_PATIENT_EVENTS, COLLECTION_ICU_SNAPSHOTS, COLLECTION_ALERTS
from app.schemas import LiveDashboardResponse, OperationalSnapshotResponse
from app.auth import get_current_user
from app.rate_limiter import rate_limit
from app.cache import get_cached, set_cached

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

def _as_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default

def _as_int(value, default=0):
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default

@router.get("/live", response_model=LiveDashboardResponse, dependencies=[Depends(rate_limit)])
async def get_live_metrics(current_user: dict = Depends(get_current_user)):
    """Calculates live metrics for the last 60 minutes based on the latest event timestamp."""
    # Check cache first
    cached_val = get_cached("dashboard:live")
    if cached_val:
        return LiveDashboardResponse(**cached_val)

    db = get_database()
    
    # Get the latest patient event to establish the simulation "current time"
    latest_event = await db[COLLECTION_PATIENT_EVENTS].find_one(sort=[("parsed_timestamp", -1)])
    
    if not latest_event:
        # If DB is empty, return default placeholders
        res = LiveDashboardResponse(
            timestamp=datetime.now().strftime("%d-%m-%Y %H:%M"),
            patients_per_hour=0,
            icu_beds_free=0,
            avg_wait_time=0.0,
            active_alerts_count=0,
            overload_status=False
        )
        set_cached("dashboard:live", res.model_dump(), ttl_seconds=5)
        return res
        
    now_sim = latest_event["parsed_timestamp"]
    one_hour_ago = now_sim - timedelta(minutes=60)
    
    # 1. Total patients in the last hour
    patients_count = await db[COLLECTION_PATIENT_EVENTS].count_documents({
        "parsed_timestamp": {"$gte": one_hour_ago, "$lte": now_sim}
    })
    
    # 2. Avg wait time in the last hour
    pipeline = [
        {"$match": {"parsed_timestamp": {"$gte": one_hour_ago, "$lte": now_sim}}},
        {"$group": {"_id": None, "avg_wait": {"$avg": "$wait_time"}}}
    ]
    cursor = db[COLLECTION_PATIENT_EVENTS].aggregate(pipeline)
    avg_results = await cursor.to_list(length=1)
    avg_wait = float(avg_results[0]["avg_wait"]) if avg_results else 0.0
    
    # 3. Latest ICU snapshot beds free
    latest_icu = await db[COLLECTION_ICU_SNAPSHOTS].find_one(sort=[("parsed_timestamp", -1)])
    icu_free = int(latest_icu["icu_beds_available"]) if latest_icu else 0
    
    # 4. Active alerts in the last hour
    alerts_count = await db[COLLECTION_ALERTS].count_documents({
        "parsed_timestamp": {"$gte": one_hour_ago, "$lte": now_sim}
    })
    
    res = LiveDashboardResponse(
        timestamp=now_sim.strftime("%d-%m-%Y %H:%M"),
        patients_per_hour=patients_count,
        icu_beds_free=icu_free,
        avg_wait_time=round(avg_wait, 2),
        active_alerts_count=alerts_count,
        overload_status=alerts_count > 0
    )
    set_cached("dashboard:live", res.model_dump(), ttl_seconds=5)
    return res

@router.get("/operations", response_model=OperationalSnapshotResponse, dependencies=[Depends(rate_limit)])
async def get_operational_snapshot(current_user: dict = Depends(get_current_user)):
    """Returns a control-tower view of the hospital event pipeline and live capacity posture."""
    db = get_database()

    latest_event = await db[COLLECTION_PATIENT_EVENTS].find_one(sort=[("parsed_timestamp", -1)])
    latest_icu = await db[COLLECTION_ICU_SNAPSHOTS].find_one(sort=[("parsed_timestamp", -1)])

    if latest_event and latest_event.get("parsed_timestamp"):
        now_sim = latest_event["parsed_timestamp"]
    else:
        now_sim = datetime.now()

    one_hour_ago = now_sim - timedelta(hours=1)
    match_window = {"parsed_timestamp": {"$gte": one_hour_ago, "$lte": now_sim}}

    patients_count = await db[COLLECTION_PATIENT_EVENTS].count_documents(match_window)
    admitted_count = await db[COLLECTION_PATIENT_EVENTS].count_documents({
        **match_window,
        "admitted": True
    })
    alerts_count = await db[COLLECTION_ALERTS].count_documents(match_window)

    event = latest_event or {}
    icu = latest_icu or {}

    icu_free = _as_int(icu.get("icu_beds_available", event.get("icu_beds_available")), 0)
    general_free = _as_int(event.get("general_beds_available"), max(0, 160 - admitted_count))
    doctors = _as_int(event.get("doctor_availability"), 0)
    nurses = _as_int(event.get("nurse_availability"), max(0, doctors * 2))
    oxygen = _as_float(icu.get("oxygen_utilization", event.get("oxygen_utilization")), 0.0)
    ambulances = _as_int(icu.get("ambulance_requests", event.get("ambulance_requests")), 0)
    ventilators = _as_int(event.get("ventilator_availability"), max(0, icu_free // 3))

    raw_load = _as_float(event.get("hospital_load_index"), patients_count * 4 + oxygen * 0.25)
    raw_capacity_risk = _as_float(
        event.get("capacity_risk_score"),
        (patients_count * 3.5) + max(0, 20 - icu_free) * 2 + max(0, oxygen - 80)
    )
    raw_overload_risk = _as_float(
        event.get("overload_risk_score"),
        raw_capacity_risk + alerts_count * 12 + max(0, ambulances - 6) * 3
    )

    hospital_load_index = round(min(100.0, raw_load), 2)
    capacity_risk_score = round(min(100.0, raw_capacity_risk), 2)
    overload_risk_score = round(min(100.0, raw_overload_risk), 2)

    if not latest_event:
        state = "Awaiting Live Data"
    elif overload_risk_score >= 75 or alerts_count > 0:
        state = "Critical Surge Watch"
    elif overload_risk_score >= 55 or icu_free <= 8:
        state = "Elevated Pressure"
    else:
        state = "Stable Operations"

    recommendations = []
    if icu_free <= 8:
        recommendations.append("Prepare ICU step-down transfers and reserve ventilators for high-acuity arrivals.")
    if ambulances >= 7:
        recommendations.append("Stage ambulance intake and notify emergency triage lead.")
    if oxygen >= 85:
        recommendations.append("Audit oxygen manifold pressure and replenish cylinders before the next peak window.")
    if doctors <= 8:
        recommendations.append("Escalate backup clinician roster for the next two hours.")
    if not recommendations:
        recommendations.append("Maintain normal routing while the prediction engine watches for surge drift.")

    return OperationalSnapshotResponse(
        timestamp=now_sim.strftime("%d-%m-%Y %H:%M"),
        digital_twin_state=state,
        hospital_load_index=hospital_load_index,
        capacity_risk_score=capacity_risk_score,
        overload_risk_score=overload_risk_score,
        bed_capacity={
            "icu_free": icu_free,
            "general_free": general_free,
            "admitted_last_hour": admitted_count,
            "patient_events_last_hour": patients_count,
        },
        staff={
            "doctors_available": doctors,
            "nurses_available": nurses,
            "status": "Lean" if doctors <= 8 else "Ready",
        },
        emergency_resources={
            "ambulance_requests": ambulances,
            "oxygen_utilization": oxygen,
            "ventilators_available": ventilators,
            "severity_level": _as_int(event.get("emergency_severity_level"), 0),
        },
        kafka_topics=[
            {"name": "hospital.patient.admission", "status": "streaming" if latest_event else "waiting", "events": patients_count},
            {"name": "hospital.resource.icu", "status": "streaming" if latest_icu else "waiting", "events": 1 if latest_icu else 0},
            {"name": "hospital.ambulance.request", "status": "active" if ambulances else "quiet", "events": ambulances},
            {"name": "hospital.prediction.events", "status": "active", "events": patients_count},
            {"name": "hospital.audit.logs", "status": "active", "events": alerts_count},
        ],
        service_layers=[
            {"name": "Admission Consumer", "description": "Normalizes patient flow and admission events"},
            {"name": "ICU Consumer", "description": "Tracks ICU beds, oxygen, ventilators, and ambulance pressure"},
            {"name": "ML Prediction Service", "description": "Forecasts bed occupancy and classifies admission risk"},
            {"name": "Alert Engine", "description": "Raises overload and resource escalation alerts"},
            {"name": "Report Analytics", "description": "Feeds KPIs, heatmaps, and historical reporting"},
        ],
        security_controls=[
            {"name": "JWT Access Tokens", "status": "planned"},
            {"name": "RBAC Authorization", "status": "planned"},
            {"name": "Rate Limiting", "status": "planned"},
            {"name": "Audit Logging", "status": "active"},
        ],
        data_sources=[
            {"name": "WHO Capacity Data", "status": "reference"},
            {"name": "Kaggle ER Dataset", "status": "training"},
            {"name": "Synthetic Live Generator", "status": "active"},
        ],
        recommendations=recommendations
    )

from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime, timedelta
from app.db import get_database, COLLECTION_PATIENT_EVENTS, COLLECTION_ICU_SNAPSHOTS, COLLECTION_ALERTS
from app.schemas import LiveDashboardResponse

router = APIRouter(prefix="/dashboard", tags=["dashboard"])

@router.get("/live", response_model=LiveDashboardResponse)
async def get_live_metrics():
    """Calculates live metrics for the last 60 minutes based on the latest event timestamp."""
    db = get_database()
    
    # Get the latest patient event to establish the simulation "current time"
    latest_event = await db[COLLECTION_PATIENT_EVENTS].find_one(sort=[("parsed_timestamp", -1)])
    
    if not latest_event:
        # If DB is empty, return default placeholders
        return LiveDashboardResponse(
            timestamp=datetime.now().strftime("%d-%m-%Y %H:%M"),
            patients_per_hour=0,
            icu_beds_free=0,
            avg_wait_time=0.0,
            active_alerts_count=0,
            overload_status=False
        )
        
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
    
    return LiveDashboardResponse(
        timestamp=now_sim.strftime("%d-%m-%Y %H:%M"),
        patients_per_hour=patients_count,
        icu_beds_free=icu_free,
        avg_wait_time=round(avg_wait, 2),
        active_alerts_count=alerts_count,
        overload_status=alerts_count > 0
    )

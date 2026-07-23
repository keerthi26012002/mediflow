import datetime
import numpy as np
from typing import List, Dict, Any
from app.db import get_database

COLLECTION_ANOMALIES = "anomalies"
COLLECTION_CAPACITY_METRICS = "capacity_metrics"
COLLECTION_HOSPITAL_STATE = "hospital_state"

async def detect_anomalies(current_twin: Dict[str, Any], current_metrics: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Analyzes live Digital Twin values against moving historical averages
    to flag operational and statistical anomalies.
    """
    db = get_database()
    ts_str = current_twin.get("timestamp")
    try:
        parsed_now = datetime.datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S.%f")
    except ValueError:
        try:
            parsed_now = datetime.datetime.strptime(ts_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            parsed_now = datetime.datetime.now()

    # Query last 100 capacity records to establish baseline mean and std
    one_day_ago = parsed_now - datetime.timedelta(hours=24)
    cursor = db["capacity_metrics_history"].find({
        "parsed_timestamp": {"$gte": one_day_ago, "$lt": parsed_now}
    }).sort([("parsed_timestamp", -1)]).limit(100)
    
    history_metrics = await cursor.to_list(length=100)
    
    # Query last 100 state records
    state_cursor = db["hospital_state_history"].find({
        "parsed_timestamp": {"$gte": one_day_ago, "$lt": parsed_now}
    }).sort([("parsed_timestamp", -1)]).limit(100)
    history_states = await state_cursor.to_list(length=100)

    anomalies = []

    # Helper function to compute anomaly
    def check_z_score(history_vals: List[float], current_val: float, metric_label: str, threshold: float = 3.0) -> Dict[str, Any]:
        if len(history_vals) < 10:
            return None # Not enough history for statistics
            
        mean = float(np.mean(history_vals))
        std = float(np.std(history_vals))
        
        if std == 0.0:
            return None
            
        z = (current_val - mean) / std
        if abs(z) > threshold:
            direction = "spike" if z > 0 else "drop"
            return {
                "timestamp": ts_str,
                "parsed_timestamp": parsed_now,
                "metric_name": metric_label,
                "current_value": round(current_val, 2),
                "rolling_mean": round(mean, 2),
                "rolling_std": round(std, 2),
                "z_score": round(z, 2),
                "description": f"Abnormal {metric_label} {direction} detected: {round(current_val, 2)} (z-score: {round(z, 2)})"
            }
        return None

    # Check admissions
    adm_hist = [float(h.get("current_admissions", 0)) for h in history_states if h.get("current_admissions") is not None]
    adm_curr = float(current_twin.get("current_admissions", 0))
    anom_adm = check_z_score(adm_hist, adm_curr, "admissions_count", threshold=2.5)
    if anom_adm:
        anomalies.append(anom_adm)

    # Check ICU occupied
    icu_hist = [float(h.get("icu_beds_occupied", 0)) for h in history_states if h.get("icu_beds_occupied") is not None]
    icu_curr = float(current_twin.get("icu_beds_occupied", 0))
    anom_icu = check_z_score(icu_hist, icu_curr, "icu_occupancy", threshold=2.5)
    if anom_icu:
        anomalies.append(anom_icu)

    # Check Oxygen utilization
    oxy_hist = [float(h.get("oxygen_utilization", 0)) for h in history_states if h.get("oxygen_utilization") is not None]
    oxy_curr = float(current_twin.get("oxygen_utilization", 0.0))
    anom_oxy = check_z_score(oxy_hist, oxy_curr, "oxygen_utilization", threshold=3.0)
    if anom_oxy:
        anomalies.append(anom_oxy)

    # Check wait time
    wait_hist = [float(h.get("average_length_of_stay", 4.2)) for h in history_metrics] # proxy or waiting queue
    queue_hist = [float(h.get("waiting_queue_index", 0)) for h in history_metrics]
    queue_curr = float(current_metrics.get("waiting_queue_index", 0.0))
    anom_queue = check_z_score(queue_hist, queue_curr, "waiting_queue_index", threshold=2.5)
    if anom_queue:
        anomalies.append(anom_queue)

    # Save anomalies to MongoDB
    if anomalies:
        await db[COLLECTION_ANOMALIES].insert_many(anomalies)

    return anomalies

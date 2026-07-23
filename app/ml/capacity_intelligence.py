import datetime
from typing import List, Dict, Any

# Total capacities
TOTAL_GENERAL_BEDS = 300
TOTAL_ICU_BEDS = 50
TOTAL_DOCTORS = 40
TOTAL_NURSES = 80
TOTAL_VENTILATORS = 25

def calculate_capacity_metrics(
    state: Dict[str, Any], 
    recent_events: List[Dict[str, Any]], 
    recent_capacity_history: List[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Computes 25 advanced Hospital Capacity Intelligence metrics based on
    the authoritative Digital Twin state and recent events, including historical moving averages.
    """
    # Parse timestamp
    state_ts_str = state.get("timestamp", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    try:
        parsed_time = datetime.datetime.strptime(state_ts_str, "%Y-%m-%d %H:%M:%S.%f")
    except ValueError:
        try:
            parsed_time = datetime.datetime.strptime(state_ts_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            parsed_time = datetime.datetime.now()

    # 1. Utilizations strictly from Digital Twin
    general_beds_occupied = state.get("general_beds_occupied", 0)
    bed_util = (general_beds_occupied / TOTAL_GENERAL_BEDS) * 100

    icu_beds_occupied = state.get("icu_beds_occupied", 0)
    icu_util = (icu_beds_occupied / TOTAL_ICU_BEDS) * 100

    doc_avail = state.get("doctors_available", TOTAL_DOCTORS)
    doctors_occupied = max(0, TOTAL_DOCTORS - doc_avail)
    doc_util = (doctors_occupied / TOTAL_DOCTORS) * 100

    nurse_avail = state.get("nurses_available", TOTAL_NURSES)
    nurses_occupied = max(0, TOTAL_NURSES - nurse_avail)
    nurse_util = (nurses_occupied / TOTAL_NURSES) * 100

    oxygen_util = state.get("oxygen_utilization", 50.0)

    ventilators_available = state.get("ventilators_available", TOTAL_VENTILATORS)
    ventilators_occupied = max(0, TOTAL_VENTILATORS - ventilators_available)
    vent_util = (ventilators_occupied / TOTAL_VENTILATORS) * 100

    # 2. Inflow / Outflow & Turnover from recent events
    admissions_count = sum(1 for e in recent_events if e.get("admitted") is True or e.get("action") == "ADMITTED")
    arrivals_count = len(recent_events)
    discharges_count = sum(1 for e in recent_events if e.get("discharged") is True or e.get("action") == "DISCHARGED")
    
    patient_turnover_rate = float(admissions_count + discharges_count)
    admission_rate = float(admissions_count)
    discharge_rate = float(discharges_count)
    average_length_of_stay = 4.2 # baseline average stay hours

    # 3. Queue and waiting parameters
    patients_waiting = state.get("patients_waiting", 0)
    waiting_queue_index = (patients_waiting / 20.0) * 100
    waiting_queue_index = max(0.0, min(100.0, waiting_queue_index))

    # Resource Burn Rate: change in oxygen consumption in the last hour
    resource_burn_rate = 0.0
    if recent_capacity_history:
        # Sort history to find the oldest matching metric in the 1-hour window
        limit_1h = parsed_time - datetime.timedelta(hours=1)
        valid_items = []
        for item in recent_capacity_history:
            item_time = item.get("parsed_timestamp")
            if isinstance(item_time, str):
                try:
                    item_time = datetime.datetime.strptime(item_time, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    item_time = None
            if item_time and item_time >= limit_1h:
                valid_items.append((item_time, item.get("oxygen_utilization", 50.0)))
        if valid_items:
            valid_items.sort(key=lambda x: x[0])
            resource_burn_rate = float(oxygen_util - valid_items[0][1])

    # 4. Stress and Pressure Indices
    hospital_load_index = (bed_util * 0.3 + icu_util * 0.3 + doc_util * 0.2 + nurse_util * 0.2)
    hospital_load_index = max(0.0, min(100.0, hospital_load_index))

    capacity_score = max(0.0, 100.0 - hospital_load_index)

    resource_pressure_index = (bed_util * 0.4 + oxygen_util * 0.3 + vent_util * 0.3)
    resource_pressure_index = max(0.0, min(100.0, resource_pressure_index))

    staff_util = (doc_util * 0.4 + nurse_util * 0.6)
    staff_fatigue_index = staff_util * 1.15
    staff_fatigue_index = max(0.0, min(100.0, staff_fatigue_index))

    hospital_stress_index = (icu_util * 0.35 + bed_util * 0.25 + waiting_queue_index * 0.25 + staff_fatigue_index * 0.15)
    hospital_stress_index = max(0.0, min(100.0, hospital_stress_index))

    # Wait times
    wait_times = [e.get("wait_time", 0) for e in recent_events if "wait_time" in e]
    avg_wait_time = (sum(wait_times) / len(wait_times)) if wait_times else 0.0
    critical_count = sum(1 for e in recent_events if e.get("emergency_severity_level") in [1, 2] or e.get("triage_level") in ["Critical", "Urgent"])
    critical_patient_ratio = (critical_count / len(recent_events) * 100.0) if recent_events else 0.0

    emergency_pressure_index = (avg_wait_time * 0.4 + arrivals_count * 2.0 + critical_patient_ratio * 0.3)
    emergency_pressure_index = max(0.0, min(100.0, emergency_pressure_index))

    surge_index = (arrivals_count / 10.0) * 100.0
    surge_index = max(0.0, min(100.0, surge_index))

    hospital_readiness_score = 100.0 - (hospital_load_index * 0.5 + emergency_pressure_index * 0.5)
    hospital_readiness_score = max(0.0, min(100.0, hospital_readiness_score))

    # Capacity Trend: rate of change of capacity score over the last hour
    capacity_trend = 0.0
    if recent_capacity_history:
        limit_1h = parsed_time - datetime.timedelta(hours=1)
        valid_items = []
        for item in recent_capacity_history:
            item_time = item.get("parsed_timestamp")
            if isinstance(item_time, str):
                try:
                    item_time = datetime.datetime.strptime(item_time, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    item_time = None
            if item_time and item_time >= limit_1h:
                valid_items.append((item_time, item.get("capacity_score", 100.0)))
        if valid_items:
            valid_items.sort(key=lambda x: x[0])
            capacity_trend = float(capacity_score - valid_items[0][1])

    # Resource Availability Score
    resource_availability_score = 100.0 - resource_pressure_index

    # Overall Hospital Health Score
    overall_health_score = (hospital_readiness_score * 0.4 + capacity_score * 0.3 + resource_availability_score * 0.2 + (100.0 - staff_fatigue_index) * 0.1)
    overall_health_score = max(0.0, min(100.0, overall_health_score))

    # 5. Bottleneck Detection
    bottlenecks = []
    if icu_util > 90.0:
        bottlenecks.append("ICU Capacity Exhausted")
    if bed_util > 90.0:
        bottlenecks.append("General Beds Congestion")
    if doc_util > 85.0 or nurse_util > 85.0:
        bottlenecks.append("Critical Staff Shortage")
    if oxygen_util > 85.0:
        bottlenecks.append("High Oxygen Burn Rate")
    if vent_util > 90.0:
        bottlenecks.append("Ventilator Depletion")
    if avg_wait_time > 45.0:
        bottlenecks.append("ER Wait Time Bottleneck")
    if patients_waiting > 15:
        bottlenecks.append("Emergency Admissions Backlog")

    bottleneck_detected = ", ".join(bottlenecks) if bottlenecks else "NOMINAL"

    # Helper function to compute moving averages for key metrics
    def get_moving_average(history: List[Dict[str, Any]], current_val: float, key: str) -> Dict[str, float]:
        windows = {
            "5m": datetime.timedelta(minutes=5),
            "15m": datetime.timedelta(minutes=15),
            "1h": datetime.timedelta(hours=1),
            "6h": datetime.timedelta(hours=6),
            "24h": datetime.timedelta(hours=24)
        }
        averages = {}
        for name, delta in windows.items():
            vals = [current_val]
            limit_time = parsed_time - delta
            if history:
                for item in history:
                    item_time = item.get("parsed_timestamp")
                    if isinstance(item_time, str):
                        try:
                            item_time = datetime.datetime.strptime(item_time, "%Y-%m-%d %H:%M:%S")
                        except ValueError:
                            item_time = None
                    if item_time and item_time >= limit_time:
                        val = item.get(key)
                        if val is not None:
                            vals.append(float(val))
            averages[name] = round(sum(vals) / len(vals), 2)
        return averages

    # Calculate moving averages for hospital load index and readiness score
    load_ma = get_moving_average(recent_capacity_history, hospital_load_index, "hospital_load_index")
    readiness_ma = get_moving_average(recent_capacity_history, hospital_readiness_score, "hospital_readiness_score")

    return {
        "timestamp": state_ts_str,
        "hospital_load_index": round(hospital_load_index, 2),
        "hospital_load_index_ma_5m": load_ma["5m"],
        "hospital_load_index_ma_15m": load_ma["15m"],
        "hospital_load_index_ma_1h": load_ma["1h"],
        "hospital_load_index_ma_6h": load_ma["6h"],
        "hospital_load_index_ma_24h": load_ma["24h"],
        "capacity_score": round(capacity_score, 2),
        "hospital_readiness_score": round(hospital_readiness_score, 2),
        "hospital_readiness_score_ma_5m": readiness_ma["5m"],
        "hospital_readiness_score_ma_15m": readiness_ma["15m"],
        "hospital_readiness_score_ma_1h": readiness_ma["1h"],
        "hospital_readiness_score_ma_6h": readiness_ma["6h"],
        "hospital_readiness_score_ma_24h": readiness_ma["24h"],
        "resource_pressure_index": round(resource_pressure_index, 2),
        "bed_utilization": round(bed_util, 2),
        "icu_utilization": round(icu_util, 2),
        "doctor_utilization": round(doc_util, 2),
        "nurse_utilization": round(nurse_util, 2),
        "oxygen_utilization": round(oxygen_util, 2),
        "ventilator_utilization": round(vent_util, 2),
        "patient_turnover_rate": round(patient_turnover_rate, 2),
        "admission_rate": round(admission_rate, 2),
        "discharge_rate": round(discharge_rate, 2),
        "average_length_of_stay": round(average_length_of_stay, 2),
        "waiting_queue_index": round(waiting_queue_index, 2),
        "resource_burn_rate": round(resource_burn_rate, 2),
        "hospital_stress_index": round(hospital_stress_index, 2),
        "emergency_pressure_index": round(emergency_pressure_index, 2),
        "surge_index": round(surge_index, 2),
        "critical_patient_ratio": round(critical_patient_ratio, 2),
        "capacity_trend": round(capacity_trend, 2),
        "bottleneck_detected": bottleneck_detected,
        "staff_fatigue_index": round(staff_fatigue_index, 2),
        "resource_availability_score": round(resource_availability_score, 2),
        "overall_health_score": round(overall_health_score, 2)
    }


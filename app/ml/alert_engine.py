from typing import List, Dict, Any
import datetime

TOTAL_GENERAL_BEDS = 300
TOTAL_ICU_BEDS = 50
TOTAL_DOCTORS = 40
TOTAL_NURSES = 80
TOTAL_VENTILATORS = 25

def check_alerts_and_recommendations(
    state: Dict[str, Any], 
    metrics: Dict[str, Any], 
    predictions: Dict[str, Any],
    policy: str = "DEFAULT"
) -> Dict[str, Any]:
    """
    Evaluates current metrics and multi-horizon predictions to generate
    hybrid (Rule + AI) alerts and operational decision support recommendations.
    Prioritizes and ranks recommendations based on hospital policies.
    """
    timestamp = state.get("timestamp", datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    alerts = []
    recommendations = []
    
    # 1. ------------------ RULE-BASED ALERTS ------------------
    # Bed utilization
    bed_util = metrics.get("bed_utilization", 0.0)
    if bed_util > 90.0:
        alerts.append({
            "timestamp": timestamp,
            "alert_type": "RULE",
            "message": f"Critical Bed Utilization: {bed_util}% general occupancy.",
            "severity": "CRITICAL",
            "confidence": 1.0,
            "department": "General Medicine",
            "predicted_impact": "Incoming ER patients will experience board congestion.",
            "estimated_time_until_overload": "0 minutes (Immediate)",
            "recommended_action": "Open North Overflow Ward immediately."
        })

    # ICU utilization
    icu_util = metrics.get("icu_utilization", 0.0)
    if icu_util > 95.0:
        alerts.append({
            "timestamp": timestamp,
            "alert_type": "RULE",
            "message": f"ICU Gridlock: {icu_util}% of ICU beds occupied.",
            "severity": "CRITICAL",
            "confidence": 1.0,
            "department": "Intensive Care",
            "predicted_impact": "High-risk surgical transfers will be blocked.",
            "estimated_time_until_overload": "0 minutes (Immediate)",
            "recommended_action": "Reroute critical ambulance transfers."
        })

    # Oxygen depletion
    oxygen_util = state.get("oxygen_utilization", 50.0)
    if oxygen_util > 85.0:
        alerts.append({
            "timestamp": timestamp,
            "alert_type": "RULE",
            "message": f"Oxygen Supply Pressure: Utilization is at {oxygen_util}%.",
            "severity": "CRITICAL",
            "confidence": 1.0,
            "department": "Logistics & Facilities",
            "predicted_impact": "Risk of pressure drop in central oxygen delivery lines.",
            "estimated_time_until_overload": "0 minutes (Immediate)",
            "recommended_action": "Connect secondary liquid oxygen manifold."
        })

    # Staff shortage
    doc_util = metrics.get("doctor_utilization", 0.0)
    nurse_util = metrics.get("nurse_utilization", 0.0)
    if doc_util > 90.0 or nurse_util > 90.0:
        alerts.append({
            "timestamp": timestamp,
            "alert_type": "RULE",
            "message": f"Severe Staff Stress: Docs utilization {doc_util}%, Nurses {nurse_util}%.",
            "severity": "WARNING",
            "confidence": 1.0,
            "department": "Clinical Staffing",
            "predicted_impact": "Extended patient waiting times and care delivery delays.",
            "estimated_time_until_overload": "0 minutes (Immediate)",
            "recommended_action": "Recall on-call backup team."
        })

    # 2. ------------------ AI-DRIVEN PREDICTIVE ALERTS ------------------
    horizons = ["30m", "1h", "6h", "24h"]
    horizon_readable = {
        "30m": "30 minutes",
        "1h": "1 hour",
        "6h": "6 hours",
        "24h": "24 hours"
    }

    # AI Bed Shortage
    beds_preds = predictions.get("beds_required", {})
    for h in horizons:
        h_pred = beds_preds.get(h, {})
        val = h_pred.get("value", 0.0)
        if val >= (TOTAL_GENERAL_BEDS - 10):
            alerts.append({
                "timestamp": timestamp,
                "alert_type": "AI",
                "message": f"Predictive General Bed Shortage: Forecasted occupied beds ({val}) near limit.",
                "severity": "CRITICAL" if h in ["30m", "1h"] else "WARNING",
                "confidence": 0.88 if h == "30m" else (0.82 if h == "1h" else 0.75),
                "department": "General Medicine",
                "predicted_impact": "Beds depletion leading to ER admissions gridlock.",
                "estimated_time_until_overload": horizon_readable[h],
                "recommended_action": "Delay elective admissions and schedule discharges."
            })
            break

    # AI ICU Overload
    icu_preds = predictions.get("icu_beds_required", {})
    for h in horizons:
        h_pred = icu_preds.get(h, {})
        val = h_pred.get("value", 0.0)
        if val >= (TOTAL_ICU_BEDS - 2):
            alerts.append({
                "timestamp": timestamp,
                "alert_type": "AI",
                "message": f"Predictive ICU Overload: ICU demand forecasted to hit {val} beds.",
                "severity": "CRITICAL",
                "confidence": 0.85 if h in ["30m", "1h"] else 0.70,
                "department": "Intensive Care",
                "predicted_impact": "Critical patients transfer delay and surgical board block.",
                "estimated_time_until_overload": horizon_readable[h],
                "recommended_action": "Identify stable patients for transfer out of ICU."
            })
            break

    # AI Staff Shortage
    docs_preds = predictions.get("doctors_required", {})
    nurses_preds = predictions.get("nurses_required", {})
    for h in horizons:
        d_val = docs_preds.get(h, {}).get("value", 0.0)
        n_val = nurses_preds.get(h, {}).get("value", 0.0)
        if d_val >= TOTAL_DOCTORS * 0.9 or n_val >= TOTAL_NURSES * 0.9:
            alerts.append({
                "timestamp": timestamp,
                "alert_type": "AI",
                "message": f"Predictive Staff Shortage: Required Docs={round(d_val,1)}, Nurses={round(n_val,1)}.",
                "severity": "WARNING",
                "confidence": 0.80,
                "department": "Clinical Staffing",
                "predicted_impact": "Nurse-to-patient ratio threshold breach.",
                "estimated_time_until_overload": horizon_readable[h],
                "recommended_action": "Request backup shifts allocation."
            })
            break

    # AI Oxygen Depletion & Ventilator Shortages
    oxy_preds = predictions.get("oxygen_required", {})
    vent_preds = predictions.get("ventilators_required", {})
    for h in horizons:
        o_val = oxy_preds.get(h, {}).get("value", 0.0)
        v_val = vent_preds.get(h, {}).get("value", 0.0)
        if o_val > 80.0 or v_val >= (TOTAL_VENTILATORS - 2):
            alerts.append({
                "timestamp": timestamp,
                "alert_type": "AI",
                "message": f"Predictive Logistics Warning: Forecasted Oxygen={o_val}%, Ventilator Occupancy={v_val}.",
                "severity": "CRITICAL" if o_val > 85.0 else "WARNING",
                "confidence": 0.78,
                "department": "Logistics & Facilities",
                "predicted_impact": "Respiratory care capacity limits reached.",
                "estimated_time_until_overload": horizon_readable[h],
                "recommended_action": "Request emergency delivery of ventilators."
            })
            break

    # AI Emergency Surge
    queue_preds = predictions.get("queue_required", {})
    for h in horizons:
        q_val = queue_preds.get(h, {}).get("value", 0.0)
        if q_val > 15.0:  # high patients waiting forecast
            alerts.append({
                "timestamp": timestamp,
                "alert_type": "AI",
                "message": f"AI Emergency Surge Alert: ER wait queue is predicted to surge to {q_val} patients.",
                "severity": "WARNING",
                "confidence": 0.82,
                "department": "Emergency",
                "predicted_impact": "ER waiting room congestion and patient dissatisfaction.",
                "estimated_time_until_overload": horizon_readable[h],
                "recommended_action": "Increase triage nurses shift density."
            })
            break

    # AI Hospital Stress Escalation
    load_preds = predictions.get("load_required", {})
    for h in horizons:
        l_val = load_preds.get(h, {}).get("value", 0.0)
        if l_val > 80.0:
            alerts.append({
                "timestamp": timestamp,
                "alert_type": "AI",
                "message": f"AI Hospital Stress Escalation: Forecasted Load Index is critical ({round(l_val, 1)}).",
                "severity": "CRITICAL",
                "confidence": 0.84,
                "department": "Administration",
                "predicted_impact": "Systemic care bottlenecks and protocol triggers.",
                "estimated_time_until_overload": horizon_readable[h],
                "recommended_action": "Hold incident command briefing."
            })
            break

    # 3. ------------------ DECISION SUPPORT RECOMMENDATIONS ------------------
    # Open Overflow Ward
    beds_val_1h = beds_preds.get("1h", {}).get("value", 0.0)
    if bed_util > 85.0 or beds_val_1h > (TOTAL_GENERAL_BEDS * 0.88):
        recommendations.append({
            "timestamp": timestamp,
            "recommendation_type": "BED_MANAGEMENT",
            "message": "Open the North Overflow Ward to increase capacity by 20 beds.",
            "reasoning": f"Current general beds utilization is {round(bed_util, 1)}% and predicted to stay high ({round(beds_val_1h, 1)}) in the next hour.",
            "expected_operational_benefit": "Reduces boarding delays in the Emergency Department.",
            "confidence_score": 0.90,
            "urgency_level": "IMMEDIATE" if bed_util > 90.0 else "HIGH",
            "estimated_improvement": "Expected waiting time reduction: 15 minutes.",
            "impact_score": 85.0,
            "urgency_score": 90.0 if bed_util > 90.0 else 75.0
        })

    # Call Additional Doctors
    docs_val_1h = docs_preds.get("1h", {}).get("value", 0.0)
    if doc_util > 80.0 or docs_val_1h > (TOTAL_DOCTORS * 0.85):
        recommendations.append({
            "timestamp": timestamp,
            "recommendation_type": "STAFFING",
            "message": "Assign backup on-call physicians to active duty.",
            "reasoning": f"Current doctor utilization is {round(doc_util, 1)}% with predicted demand of {round(docs_val_1h, 1)} doctors in the next hour.",
            "expected_operational_benefit": "Accelerates patient consultations and ER discharge clearances.",
            "confidence_score": 0.85,
            "urgency_level": "HIGH",
            "estimated_improvement": "Increases patient turnover by 12%.",
            "impact_score": 75.0,
            "urgency_score": 70.0
        })

    # Increase Nursing Staff
    nurses_val_1h = nurses_preds.get("1h", {}).get("value", 0.0)
    if nurse_util > 80.0 or nurses_val_1h > (TOTAL_NURSES * 0.85):
        recommendations.append({
            "timestamp": timestamp,
            "recommendation_type": "STAFFING",
            "message": "Increase active nursing staff density for the next shift.",
            "reasoning": f"Nursing pool utilization is {round(nurse_util, 1)}%, with a predicted shift demand of {round(nurses_val_1h, 1)} nurses.",
            "expected_operational_benefit": "Maintains patient care quality standards and prevents staff fatigue.",
            "confidence_score": 0.87,
            "urgency_level": "HIGH",
            "estimated_improvement": "Restores nurse-to-patient ratio to nominal 1:4.",
            "impact_score": 75.0,
            "urgency_score": 70.0
        })

    # Delay Elective Surgeries
    if icu_util > 88.0 or bed_util > 85.0:
        recommendations.append({
            "timestamp": timestamp,
            "recommendation_type": "OPERATIONAL",
            "message": "Delay elective admissions and schedule non-critical discharges.",
            "reasoning": f"ICU and general beds utilization are high ({round(icu_util, 1)}% and {round(bed_util, 1)}%), leaving very narrow emergency capacity reserves.",
            "expected_operational_benefit": "Preserves critical capacity for emergency trauma and cardiac cases.",
            "confidence_score": 0.92,
            "urgency_level": "HIGH",
            "estimated_improvement": "Frees up 6 general beds and 2 ICU beds within 4 hours.",
            "impact_score": 90.0,
            "urgency_score": 75.0
        })

    # Transfer Patients
    if icu_util > 95.0:
        recommendations.append({
            "timestamp": timestamp,
            "recommendation_type": "PATIENT_FLOW",
            "message": "Coordinate transfer of stable ICU patients to regional health partners.",
            "reasoning": "ICU occupancy is critical (95%+), leaving no capacity for incoming critical arrivals.",
            "expected_operational_benefit": "Restores safety margin for incoming high-severity cases.",
            "confidence_score": 0.88,
            "urgency_level": "IMMEDIATE",
            "estimated_improvement": "Reduces ICU stress index by 25 points.",
            "impact_score": 95.0,
            "urgency_score": 90.0
        })

    # Request Oxygen Supply
    oxy_val_1h = oxy_preds.get("1h", {}).get("value", 0.0)
    if oxygen_util > 78.0 or oxy_val_1h > 80.0:
        recommendations.append({
            "timestamp": timestamp,
            "recommendation_type": "LOGISTICS",
            "message": "Submit emergency delivery request for liquid oxygen canisters.",
            "reasoning": f"Oxygen utilization is high ({round(oxygen_util, 1)}%) and predicted to rise to {round(oxy_val_1h, 1)}% in the next hour.",
            "expected_operational_benefit": "Prevents manifold pressure drops and ensures continuous respiratory support.",
            "confidence_score": 0.95,
            "urgency_level": "HIGH",
            "estimated_improvement": "Restores backup reserve tank levels to 100%.",
            "impact_score": 80.0,
            "urgency_score": 80.0
        })

    # Request Ambulances
    amb_val_1h = predictions.get("ambulances_required", {}).get("1h", {}).get("value", 0.0)
    if state.get("ambulances_active", 0) > 7 or amb_val_1h > 6.0:
        recommendations.append({
            "timestamp": timestamp,
            "recommendation_type": "LOGISTICS",
            "message": "Coordinate with county dispatch for secondary EMS ambulance routing.",
            "reasoning": "Local ambulance requests are peaking, which could cause emergency response delays.",
            "expected_operational_benefit": "Ensures continuous emergency response coverage for the sector.",
            "confidence_score": 0.81,
            "urgency_level": "MEDIUM",
            "estimated_improvement": "Reduces regional ambulance response times by 8 minutes.",
            "impact_score": 65.0,
            "urgency_score": 60.0
        })

    # Activate Emergency Protocol
    readiness = metrics.get("hospital_readiness_score", 100.0)
    if metrics.get("hospital_load_index", 0.0) > 80.0 or readiness < 40.0:
        recommendations.append({
            "timestamp": timestamp,
            "recommendation_type": "EMERGENCY_PROTOCOL",
            "message": "Activate Gridlock Protocol (Code Orange).",
            "reasoning": f"Overall hospital health score is critical and readiness score has dropped to {round(readiness, 1)}%.",
            "expected_operational_benefit": "Deploys incident command structure and unlocks emergency operational budgets.",
            "confidence_score": 0.94,
            "urgency_level": "IMMEDIATE",
            "estimated_improvement": "Restores hospital readiness score by 20 points in 2 hours.",
            "impact_score": 98.0,
            "urgency_score": 95.0
        })

    # Apply Policy weighting and prioritize
    for r in recommendations:
        impact = r["impact_score"]
        urgency = r["urgency_score"]
        rec_type = r["recommendation_type"]
        
        # Policy boosts
        if policy == "PRESERVE_ICU":
            if rec_type in ["PATIENT_FLOW", "OPERATIONAL"]:
                urgency += 20.0
                impact += 15.0
        elif policy == "MAXIMIZE_THROUGHPUT":
            if rec_type in ["BED_MANAGEMENT", "STAFFING"]:
                urgency += 20.0
                impact += 15.0

        # Calculate final operational benefit score
        r["benefit_score"] = round(impact * 0.6 + urgency * 0.4, 1)

    # Sort recommendations by benefit score descending
    sorted_recs = sorted(recommendations, key=lambda x: x["benefit_score"], reverse=True)
    
    # Remove temporary tracking scores for API clean payload
    for r in sorted_recs:
        r.pop("impact_score", None)
        r.pop("urgency_score", None)

    return {
        "alerts": alerts,
        "recommendations": sorted_recs
    }

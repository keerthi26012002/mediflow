import os
import joblib
import pandas as pd
from datetime import datetime, timedelta

# Paths for models (Phase 2 targets)
MODEL_DIR = os.path.join(os.path.dirname(__file__), "models")
XGB_MODEL_PATH = os.path.join(MODEL_DIR, "model_xgb.pkl")
PROPHET_MODEL_PATH = os.path.join(MODEL_DIR, "model_prophet.pkl")
DEPARTMENTS = ["Self-Referral", "Emergency", "ICU", "Cardiology", "Neurology", "Pediatrics", "Orthopedics", "General Medicine"]
ARRIVAL_MODES = ["Walk-in", "Ambulance", "Transfer"]
TRIAGE_LEVELS = ["Critical", "Urgent", "Semi-Urgent", "Non-Urgent", "Unspecified"]
FEATURE_COLS = [
    "age", "gender", "emergency_severity_level", "hour", "day_of_week",
    "is_weekend", "shift", "wait_time", "department_encoded",
    "arrival_mode_encoded", "triage_level_encoded", "icu_beds_available",
    "general_beds_available", "ambulance_requests", "doctor_availability",
    "nurse_availability", "oxygen_utilization", "ventilator_availability",
    "capacity_risk_score", "hospital_load_index", "overload_risk_score"
]

# Keep track of loaded models
_xgb_model = None
_prophet_model = None

def load_models():
    """Dynamically load models if they exist."""
    global _xgb_model, _prophet_model
    
    if os.path.exists(XGB_MODEL_PATH) and _xgb_model is None:
        try:
            _xgb_model = joblib.load(XGB_MODEL_PATH)
            print("Successfully loaded XGBoost model.")
        except Exception as e:
            print(f"Error loading XGBoost model: {e}")
            
    if os.path.exists(PROPHET_MODEL_PATH) and _prophet_model is None:
        try:
            _prophet_model = joblib.load(PROPHET_MODEL_PATH)
            print("Successfully loaded Prophet model.")
        except Exception as e:
            print(f"Error loading Prophet model: {e}")

def encode_category(value, categories):
    value = str(value)
    return categories.index(value) if value in categories else 0

def get_shift(hour: int) -> int:
    if 6 <= hour < 14:
        return 0
    if 14 <= hour < 22:
        return 1
    return 2

def parse_event_datetime(timestamp: str) -> datetime:
    for fmt in ("%d-%m-%Y %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M:%S.%f"):
        try:
            return datetime.strptime(timestamp, fmt)
        except ValueError:
            continue
    return datetime.now()

def predict_admission(event: dict) -> dict:
    """
    Predicts if a patient event will lead to admission.
    Returns details to save in MongoDB.
    """
    load_models()
    
    # In Phase 4, the model files won't exist yet, so we return the stub values.
    # In Phase 2, we will use the loaded model.
    if _xgb_model is not None:
        try:
            # Prepare feature vector from the event dictionary.
            # (Note: Feature processing logic will be fully aligned in Phase 2)
            gender_val = 1 if str(event.get("gender", "")).lower() in ("m", "male") else 0
            dt = parse_event_datetime(event.get("timestamp", ""))
            hour = dt.hour
            day_of_week = dt.weekday()
            is_weekend = 1 if day_of_week >= 5 else 0
            shift = get_shift(hour)
            
            age = float(event.get("age", 40))
            wait_time = float(event.get("wait_time", 30))
            severity = float(event.get("emergency_severity_level", 3))
            icu_beds = float(event.get("icu_beds_available", 10))
            general_beds = float(event.get("general_beds_available", 160))
            ambulance = float(event.get("ambulance_requests", 2))
            docs = float(event.get("doctor_availability", 15))
            nurses = float(event.get("nurse_availability", docs * 2))
            oxygen = float(event.get("oxygen_utilization", 70.0))
            ventilators = float(event.get("ventilator_availability", max(0, icu_beds // 3)))
            capacity_risk = float(event.get("capacity_risk_score", 0.0))
            load_index = float(event.get("hospital_load_index", 0.0))
            overload_risk = float(event.get("overload_risk_score", 0.0))
            dept_encoded = encode_category(event.get("department", "Self-Referral"), DEPARTMENTS)
            arrival_encoded = encode_category(event.get("arrival_mode", "Walk-in"), ARRIVAL_MODES)
            triage_encoded = encode_category(event.get("triage_level", "Unspecified"), TRIAGE_LEVELS)

            features = pd.DataFrame([{
                "age": age,
                "gender": gender_val,
                "emergency_severity_level": severity,
                "hour": hour,
                "day_of_week": day_of_week,
                "is_weekend": is_weekend,
                "shift": shift,
                "wait_time": wait_time,
                "department_encoded": dept_encoded,
                "arrival_mode_encoded": arrival_encoded,
                "triage_level_encoded": triage_encoded,
                "icu_beds_available": icu_beds,
                "general_beds_available": general_beds,
                "ambulance_requests": ambulance,
                "doctor_availability": docs,
                "nurse_availability": nurses,
                "oxygen_utilization": oxygen,
                "ventilator_availability": ventilators,
                "capacity_risk_score": capacity_risk,
                "hospital_load_index": load_index,
                "overload_risk_score": overload_risk
            }])
            features = features[FEATURE_COLS]
            
            # Predict
            proba = float(_xgb_model.predict_proba(features)[0][1])
            pred_admitted = bool(proba >= 0.5)
            
            # Check overload (admissions/hour threshold)
            # Overload status will also be calculated dynamically by rolling consumer count,
            # but we return our local model status as well
            return {
                "patient_id": event.get("patient_id"),
                "timestamp": event.get("timestamp"),
                "predicted_admission": pred_admitted,
                "admission_proba": proba,
                "overload": proba > 0.8, # Mocking overload flag if proba is high
                "model_loaded": True
            }
        except Exception as e:
            print(f"Error performing XGBoost inference: {e}")
            # Fallback to stub on inference error
    
    # STUB / FALLBACK
    return {
        "patient_id": event.get("patient_id", "unknown"),
        "timestamp": event.get("timestamp", ""),
        "predicted_admission": None,
        "admission_proba": None,
        "overload": False,
        "model_loaded": False
    }

def forecast_beds(hours: int = 24) -> list:
    """
    Returns a forecasted list of predicted bed occupancy for the next `hours`.
    """
    load_models()
    
    now = datetime.now()
    
    # If Prophet model is loaded, run real prediction
    if _prophet_model is not None:
        try:
            # Create future DataFrame
            future_dates = [now + timedelta(hours=i) for i in range(hours)]
            future_df = pd.DataFrame({"ds": future_dates})
            
            forecast = _prophet_model.predict(future_df)
            result = []
            for _, row in forecast.iterrows():
                result.append({
                    "ts": row["ds"].strftime("%Y-%m-%d %H:00"),
                    "predicted_occupancy": max(0, int(row["yhat"]))
                })
            return result
        except Exception as e:
            print(f"Error running Prophet forecast: {e}")
            # Fallback to stub on error
            
    # STUB / FALLBACK: Generate an oscillating mock trend
    forecast_data = []
    for i in range(hours):
        future_ts = now + timedelta(hours=i)
        # Mock sine wave for bed occupancy
        import math
        occupancy = int(25 + 10 * math.sin(i / 3.0) + (i % 5))
        forecast_data.append({
            "ts": future_ts.strftime("%Y-%m-%d %H:00"),
            "predicted_occupancy": max(0, min(50, occupancy))
        })
    return forecast_data

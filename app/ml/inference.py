import os
import joblib
import pandas as pd
from datetime import datetime, timedelta

# Paths for models (Phase 2 targets)
MODEL_DIR = os.path.join(os.path.dirname(__file__), "models")
XGB_MODEL_PATH = os.path.join(MODEL_DIR, "model_xgb.pkl")
PROPHET_MODEL_PATH = os.path.join(MODEL_DIR, "model_prophet.pkl")

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
            # Map values
            gender_val = 1 if str(event.get("gender", "")).lower() == "m" else 0
            
            # Extract datetime features
            dt = datetime.strptime(event.get("timestamp", ""), "%d-%m-%Y %H:%M")
            hour = dt.hour
            day_of_week = dt.weekday()
            is_weekend = 1 if day_of_week >= 5 else 0
            
            # Simple numeric features mapping
            age = float(event.get("age", 40))
            wait_time = float(event.get("wait_time", 30))
            severity = float(event.get("emergency_severity_level", 3))
            icu_beds = float(event.get("icu_beds_available", 10))
            ambulance = float(event.get("ambulance_requests", 2))
            docs = float(event.get("doctor_availability", 15))
            oxygen = float(event.get("oxygen_utilization", 70.0))
            
            # For category 'department', let's use a very basic encoding or mapping
            # (Phase 2 feature_engineering will build the formal dictionary)
            # Just define a list of common depts so features are aligned.
            depts = ["Self-Referral", "Cardiology", "ICU", "Emergency", "Orthopedics", "Pediatrics"]
            dept_encoded = depts.index(event.get("department", "Self-Referral")) if event.get("department") in depts else 0
            
            # Feature ordering must match training:
            features = pd.DataFrame([{
                "age": age,
                "gender": gender_val,
                "emergency_severity_level": severity,
                "hour": hour,
                "day_of_week": day_of_week,
                "is_weekend": is_weekend,
                "wait_time": wait_time,
                "department": dept_encoded,
                "icu_beds_available": icu_beds,
                "ambulance_requests": ambulance,
                "doctor_availability": docs,
                "oxygen_utilization": oxygen
            }])
            
            # Reorder columns to ensure exact match with training
            feature_cols = [
                "age", "gender", "emergency_severity_level", "hour", "day_of_week",
                "is_weekend", "wait_time", "department", "icu_beds_available",
                "ambulance_requests", "doctor_availability", "oxygen_utilization"
            ]
            features = features[feature_cols]
            
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

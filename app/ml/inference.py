import os
import json
import joblib
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# Paths for models
MODEL_DIR = os.path.join(os.path.dirname(__file__), "models")

# Model mappings
XGB_ADMISSION_PATH = os.path.join(MODEL_DIR, "model_xgb_admission.pkl")
REG_MODEL_PATHS = {
    "beds_required": os.path.join(MODEL_DIR, "model_xgb_beds.pkl"),
    "icu_beds_required": os.path.join(MODEL_DIR, "model_xgb_icu.pkl"),
    "doctors_required": os.path.join(MODEL_DIR, "model_xgb_staff_docs.pkl"),
    "nurses_required": os.path.join(MODEL_DIR, "model_xgb_staff_nurses.pkl"),
    "ventilators_required": os.path.join(MODEL_DIR, "model_xgb_ventilators.pkl"),
    "oxygen_required": os.path.join(MODEL_DIR, "model_xgb_oxygen.pkl"),
    "queue_required": os.path.join(MODEL_DIR, "model_xgb_queue.pkl"),
    "ambulances_required": os.path.join(MODEL_DIR, "model_xgb_ambulances.pkl"),
    "load_required": os.path.join(MODEL_DIR, "model_xgb_load.pkl"),
    "pressure_required": os.path.join(MODEL_DIR, "model_xgb_pressure.pkl"),
    "availability_required": os.path.join(MODEL_DIR, "model_xgb_availability.pkl")
}

PROPHET_ADMISSIONS_PATH = os.path.join(MODEL_DIR, "model_prophet_admissions.pkl")
PROPHET_DISCHARGES_PATH = os.path.join(MODEL_DIR, "model_prophet_discharges.pkl")
PROPHET_OXYGEN_PATH = os.path.join(MODEL_DIR, "model_prophet_oxygen.pkl")
PROPHET_VENTILATORS_PATH = os.path.join(MODEL_DIR, "model_prophet_ventilators.pkl")

# In-memory models and metadata cache
models_cache = {}
residual_errors = {}
feature_names = {}
_xgb_model = None
_prophet_model = None

def load_models():
    """Loads all multi-horizon regressors, classifiers, residual metadata, and forecasters."""
    global _xgb_model, _prophet_model, residual_errors, feature_names
    
    # Load metadata
    res_path = os.path.join(MODEL_DIR, "residual_errors.json")
    if os.path.exists(res_path) and not residual_errors:
        try:
            with open(res_path, "r") as f:
                residual_errors = json.load(f)
        except Exception as e:
            print(f"Error loading residual errors metadata: {e}")

    feat_path = os.path.join(MODEL_DIR, "feature_names.json")
    if os.path.exists(feat_path) and not feature_names:
        try:
            with open(feat_path, "r") as f:
                feature_names = json.load(f)
        except Exception as e:
            print(f"Error loading feature names: {e}")

    # Load classifier
    if os.path.exists(XGB_ADMISSION_PATH) and "xgb_admission" not in models_cache:
        try:
            models_cache["xgb_admission"] = joblib.load(XGB_ADMISSION_PATH)
            _xgb_model = models_cache["xgb_admission"]
        except Exception as e:
            print(f"Failed to load XGB Admission model: {e}")

    # Load regressors
    for key, path in REG_MODEL_PATHS.items():
        if os.path.exists(path) and key not in models_cache:
            try:
                models_cache[key] = joblib.load(path)
            except Exception as e:
                print(f"Failed to load regressor {key}: {e}")

    # Load Prophet models
    prophet_targets = {
        "prophet_admissions": PROPHET_ADMISSIONS_PATH,
        "prophet_discharges": PROPHET_DISCHARGES_PATH,
        "prophet_oxygen": PROPHET_OXYGEN_PATH,
        "prophet_ventilators": PROPHET_VENTILATORS_PATH
    }
    for key, path in prophet_targets.items():
        if os.path.exists(path) and key not in models_cache:
            try:
                models_cache[key] = joblib.load(path)
                if key == "prophet_admissions":
                    _prophet_model = models_cache[key]
            except Exception as e:
                print(f"Failed to load Prophet {key}: {e}")

def get_base_features_df(event: dict) -> pd.DataFrame:
    """Extracts base encoded features from the raw event mapping."""
    depts = ["Self-Referral", "Cardiology", "ICU", "Emergency", "Orthopedics", "Pediatrics", "Neurology"]
    arrival_modes = ["Walk-in", "Referral", "Ambulance", "Transfer"]
    triage_levels = ["Non-Urgent", "Semi-Urgent", "Urgent", "Critical"]
    genders = ["Female", "Male"]

    timestamp_str = event.get("timestamp", "")
    try:
        dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S.%f")
    except ValueError:
        try:
            dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            try:
                dt = datetime.strptime(timestamp_str, "%d-%m-%Y %H:%M")
            except ValueError:
                dt = datetime.now()

    hour = dt.hour
    day_of_week_encoded = dt.weekday()
    is_weekend = 1 if day_of_week_encoded >= 5 else 0

    gender_str = str(event.get("gender", "Female"))
    gender_val = 1 if "m" in gender_str.lower() else 0

    dept_str = str(event.get("department", "Self-Referral"))
    dept_encoded = depts.index(dept_str) if dept_str in depts else 0

    arrival_str = str(event.get("arrival_mode", "Walk-in"))
    arrival_mode_encoded = arrival_modes.index(arrival_str) if arrival_str in arrival_modes else 0

    triage_str = str(event.get("triage_level", "Urgent"))
    triage_level_encoded = triage_levels.index(triage_str) if triage_str in triage_levels else 2

    # Map wait time & severities
    wait_time = float(event.get("wait_time", 30.0))
    severity = float(event.get("emergency_severity_level", 3.0))

    # Base dictionary
    return pd.DataFrame([{
        "patient_id": event.get("patient_id", "unknown"),
        "timestamp": timestamp_str,
        "parsed_timestamp": dt,
        "age": float(event.get("age", 40.0)),
        "gender_encoded": gender_val,
        "dept_encoded": dept_encoded,
        "arrival_mode_encoded": arrival_mode_encoded,
        "triage_level_encoded": triage_level_encoded,
        "wait_time": wait_time,
        "emergency_severity_level": severity,
        "icu_beds_available": float(event.get("icu_beds_available", 20.0)),
        "general_beds_available": float(event.get("general_beds_available", 150.0)),
        "doctor_availability": float(event.get("doctor_availability", 20.0)),
        "nurse_availability": float(event.get("nurse_availability", 40.0)),
        "ambulance_requests": float(event.get("ambulance_requests", 3.0)),
        "oxygen_utilization": float(event.get("oxygen_utilization", 70.0)),
        "ventilator_availability": float(event.get("ventilator_availability", 10.0)),
        "capacity_risk_score": float(event.get("capacity_risk_score", 50.0)),
        "hospital_load_index": float(event.get("hospital_load_index", 35.0)),
        "overload_risk_score": float(event.get("overload_risk_score", 40.0)),
        "hour": hour,
        "day_of_week_encoded": day_of_week_encoded,
        "is_weekend": is_weekend,
        "admitted": 1 if event.get("admitted") else 0
    }])

async def extract_streaming_features(event: dict, db) -> pd.DataFrame:
    """
    Queries historical patient events from MongoDB, appends the current event,
    and runs the full rolling window feature engineering function.
    """
    base_df = get_base_features_df(event)
    parsed_time = base_df.iloc[0]["parsed_timestamp"]
    
    if db is None:
        # Return base padded features if DB connection not present
        return pad_rolling_features(base_df)

    # Ingest historical events from the last 24 hours
    one_day_ago = parsed_time - timedelta(hours=24)
    cursor = db["events"].find({
        "parsed_timestamp": {"$gte": one_day_ago, "$lt": parsed_time}
    }).sort([("parsed_timestamp", 1)])
    
    hist_events = await cursor.to_list(length=100)
    if not hist_events:
        return pad_rolling_features(base_df)

    # Format historical records into DataFrame
    hist_rows = []
    for e in hist_events:
        hist_rows.append(get_base_features_df(e))
        
    hist_df = pd.concat(hist_rows, ignore_index=True)
    combined_df = pd.concat([hist_df, base_df], ignore_index=True)
    
    # Import the rolling function from features script
    from ml.feature_engineering_v2 import calculate_rolling_features
    engineered_df = calculate_rolling_features(combined_df)
    
    # Return only the last row representing the current event with computed rolling features
    return engineered_df.tail(1)

def pad_rolling_features(df: pd.DataFrame) -> pd.DataFrame:
    """Pads rolling window features with default averages in case of cold start."""
    df["general_beds_occupied"] = 300.0 - df["general_beds_available"]
    df["icu_beds_occupied"] = 50.0 - df["icu_beds_available"]
    df["doctors_occupied"] = 40.0 - df["doctor_availability"]
    df["nurses_occupied"] = 80.0 - df["nurse_availability"]
    df["ventilators_occupied"] = 25.0 - df["ventilator_availability"]
    df["discharged"] = 0.0

    rolling_cols = [
        "rolling_adm_5m", "rolling_adm_15m", "rolling_adm_30m", "rolling_adm_1h", "rolling_adm_6h", "rolling_adm_24h",
        "rolling_dis_5m", "rolling_dis_15m", "rolling_dis_30m", "rolling_dis_1h", "rolling_dis_6h", "rolling_dis_24h",
        "velocity_1h", "velocity_6h", "velocity_24h", "accel_1h",
        "icu_growth_1h", "icu_growth_6h",
        "arrivals_count_5m", "arrivals_count_30m", "arrivals_count_1h", "arrivals_count_6h",
        "bed_turnover_rate_1h", "bed_turnover_rate_6h",
        "oxygen_trend_1h", "oxygen_trend_6h", "vent_trend_1h",
        "doc_workload_trend_1h", "nurse_workload_trend_1h",
        "patient_inflow_1h", "patient_outflow_1h",
        "emergency_growth_rate_1h",
        "avg_wait_time_1h", "avg_wait_time_6h",
        "pressure_trend_1h",
        "surge_probability",
        "beds_occupied_lag_1", "beds_occupied_lag_2", "icu_occupied_lag_1", "icu_occupied_lag_2"
    ]
    for c in rolling_cols:
        df[c] = 0.0
        
    df["beds_occupied_lag_1"] = df["general_beds_occupied"]
    df["icu_occupied_lag_1"] = df["icu_beds_occupied"]
    return df

FEATURE_BASELINES = {
    "general_beds_available": 150.0,
    "icu_beds_available": 25.0,
    "doctor_availability": 20.0,
    "nurse_availability": 40.0,
    "oxygen_utilization": 70.0,
    "ventilator_availability": 10.0,
    "wait_time": 30.0,
    "emergency_severity_level": 3.0,
    "general_beds_occupied": 150.0,
    "icu_beds_occupied": 25.0,
    "doctors_occupied": 20.0,
    "nurses_occupied": 40.0,
    "ventilators_occupied": 15.0,
    "patients_waiting": 5.0,
    "ambulances_active": 2.0,
    "hospital_load_index": 35.0,
    "overload_risk_score": 40.0,
    "resource_pressure_index": 35.0,
    "staff_fatigue_index": 45.0
}

EXPLANATION_MAP = {
    "general_beds_available": "available general beds",
    "icu_beds_available": "ICU capacity levels",
    "doctor_availability": "medical staff availability",
    "nurse_availability": "nurse staffing levels",
    "rolling_adm_1h": "recent admissions inflow",
    "rolling_adm_6h": "6-hour admissions trend",
    "rolling_adm_24h": "daily admission surge",
    "surge_probability": "surge probability indicators",
    "wait_time": "ER waiting times",
    "velocity_1h": "occupancy velocity shifts",
    "pressure_trend_1h": "hospital load pressure trends",
    "beds_occupied_lag_1": "prior hour bed occupancy",
    "general_beds_occupied": "general beds occupied",
    "icu_beds_occupied": "ICU beds occupied",
    "doctors_occupied": "doctors occupied",
    "nurses_occupied": "nurses occupied",
    "oxygen_utilization": "oxygen utilization",
    "ventilator_availability": "ventilator availability",
    "ventilators_occupied": "ventilators occupied",
    "patients_waiting": "waiting patients count",
    "ambulances_active": "active ambulance routing"
}

def generate_local_explanation_and_attributions(model, features_df, target_key: str) -> tuple:
    """
    Computes local feature importance explainability by identifying which of 
    the top features contributed most to the current prediction.
    Returns: (natural_language_reasoning, attributions_list)
    """
    if not hasattr(model, "feature_importances_"):
        return "Nominal operation trend predicted.", []
        
    importances = model.feature_importances_
    features = list(features_df.columns)
    
    # Compute local SHAP-like attributions
    raw_attributions = []
    for feat, imp in zip(features, importances):
        if imp > 0.0:
            val = float(features_df.iloc[0].get(feat, 0.0))
            base = FEATURE_BASELINES.get(feat, 0.0)
            # Deviation from baseline
            dev = val - base
            # Contribution is importance * deviation
            attr_val = dev * imp
            raw_attributions.append((feat, attr_val, imp))

    # Sort by absolute attribution value
    sorted_attributions = sorted(raw_attributions, key=lambda x: abs(x[1]), reverse=True)
    
    # Calculate percentage contributions
    total_abs = sum(abs(x[1]) for x in sorted_attributions)
    attributions_list = []
    if total_abs > 0.0:
        for feat, attr_val, imp in sorted_attributions[:5]:
            pct = (abs(attr_val) / total_abs) * 100.0
            val = float(features_df.iloc[0].get(feat, 0.0))
            attributions_list.append({
                "feature": feat,
                "display_name": EXPLANATION_MAP.get(feat, feat.replace("_", " ")),
                "percentage": round(pct, 1),
                "value": round(val, 2),
                "contribution": "positive" if attr_val >= 0 else "negative"
            })

    # Pick top drivers for the natural language reasoning
    top_feats = [x[0] for x in sorted_attributions if x[2] > 0.01][:3]
    if not top_feats:
        return "Predictive trend based on baseline historical capacity levels.", attributions_list

    readable_feats = [EXPLANATION_MAP.get(f, f.replace("_", " ")) for f in top_feats]
    
    # Extract weights for the global impact output
    feat_imp = sorted(zip(features, importances), key=lambda x: x[1], reverse=True)
    w1 = int(feat_imp[0][1] * 100)
    w2 = int(feat_imp[1][1] * 100) if len(feat_imp) > 1 else 0
    
    if len(readable_feats) == 1:
        reasoning = f"Prediction primarily driven by {readable_feats[0]} (influence: {w1}%)."
    else:
        reasoning = f"Influenced by {readable_feats[0]} ({w1}%) and {readable_feats[1]} ({w2}%)."
        
    return reasoning, attributions_list

def predict_admission(event: dict) -> dict:
    """Predicts patient admission classification (v1.0 backward compatibility)."""
    load_models()
    model = models_cache.get("xgb_admission")
    if model is not None:
        try:
            # For simplicity, extract base features
            base_df = get_base_features_df(event)
            padded = pad_rolling_features(base_df)
            
            # Match training feature cols
            cols = feature_names.get("classifier_features", list(padded.columns))
            # Ensure columns are aligned
            for c in cols:
                if c not in padded.columns:
                    padded[c] = 0.0
            feats = padded[cols]

            proba = float(model.predict_proba(feats)[0][1])
            pred_admitted = bool(proba >= 0.5)
            
            # Save this admission prediction to the DB for later validation matching if available
            try:
                from app.db import get_database
                db = get_database()
                if db is not None:
                    import asyncio
                    pid = event.get("patient_id", "unknown")
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(db["admission_predictions"].replace_one(
                            {"patient_id": pid},
                            {
                                "patient_id": pid,
                                "predicted_admission": pred_admitted,
                                "admission_proba": proba,
                                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            },
                            upsert=True
                        ))
                    except RuntimeError:
                        pass
            except Exception:
                pass

            return {
                "patient_id": event.get("patient_id", "unknown"),
                "timestamp": event.get("timestamp", ""),
                "predicted_admission": pred_admitted,
                "admission_proba": proba,
                "overload": proba > 0.8,
                "model_loaded": True
            }
        except Exception as e:
            print(f"Error in XGBoost Admission prediction: {e}")

    return {
        "patient_id": event.get("patient_id", "unknown"),
        "timestamp": event.get("timestamp", ""),
        "predicted_admission": None,
        "admission_proba": None,
        "overload": False,
        "model_loaded": False
    }

# local in-memory prediction cache
prediction_cache = {}

def get_prediction_cache_key(features_df, target_key: str, horizon: float) -> str:
    keys = ["general_beds_available", "icu_beds_available", "doctor_availability", "nurse_availability", "oxygen_utilization", "ventilator_availability"]
    parts = [target_key, str(horizon)]
    for k in keys:
        if k in features_df.columns:
            parts.append(f"{k}:{round(float(features_df.iloc[0][k]), 1)}")
    return "_".join(parts)

def predict_capacity_demands_v2(features_df) -> dict:
    """
    Continuous Prediction Engine: Runs multi-horizon inferences (30m, 1h, 6h, 24h)
    for all 11 regressor targets, generating SHAP-like explanations and confidence intervals.
    """
    global prediction_cache
    load_models()
    horizons = {"30m": 30.0, "1h": 60.0, "6h": 360.0, "24h": 1440.0}
    predictions_payload = {}

    for key, model_path in REG_MODEL_PATHS.items():
        model = models_cache.get(key)
        std_err = residual_errors.get(key, 5.0) # default fallback std err
        
        predictions_payload[key] = {}
        
        for h_name, h_val in horizons.items():
            # Check cache first
            cache_key = get_prediction_cache_key(features_df, key, h_val)
            if cache_key in prediction_cache:
                predictions_payload[key][h_name] = prediction_cache[cache_key]
                continue

            if model is not None:
                try:
                    # Construct feature vector with the horizon
                    feats = features_df.copy()
                    feats["horizon_minutes"] = h_val
                    
                    # Align features
                    cols = feature_names.get("regressor_features", list(feats.columns))
                    for c in cols:
                        if c not in feats.columns:
                            feats[c] = 0.0
                    input_vector = feats[cols]
                    
                    # Run prediction
                    val = float(model.predict(input_vector)[0])
                    # Post-process bounds
                    if key in ["beds_required", "icu_beds_required", "doctors_required", "nurses_required", "ventilators_required", "queue_required", "ambulances_required"]:
                        val = max(0.0, val)
                        if key == "beds_required": val = min(300.0, val)
                        elif key == "icu_beds_required": val = min(50.0, val)
                        elif key == "doctors_required": val = min(40.0, val)
                        elif key == "nurses_required": val = min(80.0, val)
                        elif key == "ventilators_required": val = min(25.0, val)
                    elif key in ["load_required", "pressure_required", "availability_required", "oxygen_required"]:
                        val = max(0.0, min(100.0, val))

                    # Compute 95% Confidence Interval
                    ci_lower = round(max(0.0, val - 1.96 * std_err), 1)
                    ci_upper = round(val + 1.96 * std_err, 1)
                    
                    # Generate SHAP-like explanations and attributions
                    explanation, attributions = generate_local_explanation_and_attributions(model, input_vector, key)

                    # Compute confidence score: 100 - relative standard error representation
                    denom = max(val, 1.0)
                    confidence_score = round(max(50.0, min(100.0, 100.0 - (std_err / denom) * 20.0)), 1)

                    pred_entry = {
                        "value": round(val, 1),
                        "ci": [ci_lower, ci_upper],
                        "explanation": explanation,
                        "attributions": attributions,
                        "confidence_score": confidence_score,
                        "model_version": "v2.2"
                    }
                    
                    # Store in cache
                    prediction_cache[cache_key] = pred_entry
                    predictions_payload[key][h_name] = pred_entry
                except Exception as e:
                    print(f"Error predicting {key} at horizon {h_name}: {e}")
                    predictions_payload[key][h_name] = {
                        "value": 0.0, "ci": [0.0, 0.0], "explanation": "Prediction error.", "attributions": [], "confidence_score": 50.0, "model_version": "v2.2"
                    }
            else:
                predictions_payload[key][h_name] = {
                    "value": 0.0, "ci": [0.0, 0.0], "explanation": "Model weights offline.", "attributions": [], "confidence_score": 50.0, "model_version": "v2.2"
                }

    predictions_payload["model_loaded"] = len(models_cache) > 2
    return predictions_payload

def forecast_beds(hours: int = 24) -> list:
    """Predicts future trends for the next `hours` using Prophet forecasters (v1.0 backwards compatibility)."""
    load_models()
    now = datetime.now()
    future_dates = [now + timedelta(hours=i) for i in range(hours)]
    future_df = pd.DataFrame({"ds": future_dates})
    
    forecast_data = []
    
    p_adm = models_cache.get("prophet_admissions")
    p_dis = models_cache.get("prophet_discharges")
    p_oxy = models_cache.get("prophet_oxygen")
    p_vnt = models_cache.get("prophet_ventilators")

    if p_adm is not None and p_dis is not None:
        try:
            f_adm = p_adm.predict(future_df)
            f_dis = p_dis.predict(future_df)
            f_oxy = p_oxy.predict(future_df) if p_oxy is not None else None
            
            for i in range(hours):
                adm_val = round(max(0.0, float(f_adm.iloc[i]["yhat"])), 2)
                dis_val = round(max(0.0, float(f_dis.iloc[i]["yhat"])), 2)
                oxy_val = round(max(0.0, float(f_oxy.iloc[i]["yhat"])), 2) if f_oxy is not None else 65.0
                
                # Dynamic bed occupancy trend: initial occupancy baseline (e.g. 180.0) + adm - dis
                predicted_occupancy = round(max(0.0, min(300.0, 180.0 + adm_val - dis_val)), 2)
                h_str = future_dates[i].strftime("%H:00")
                ts_str = future_dates[i].strftime("%Y-%m-%d %H:00")
                
                forecast_data.append({
                    "timestamp": h_str,
                    "hour": h_str,
                    "ts": ts_str,
                    "occupancy": predicted_occupancy,
                    "predicted_occupancy": predicted_occupancy,
                    "yhat": predicted_occupancy,
                    "inflow": adm_val,
                    "admissions": adm_val,
                    "predicted_inflow": adm_val,
                    "discharges": dis_val,
                    "oxygen": oxy_val
                })
            return forecast_data
        except Exception as e:
            print(f"Error running Prophet forecasting: {e}")

    # Fallback oscillated trend with exact float precision
    for i in range(hours):
        future_ts = now + timedelta(hours=i)
        occupancy = round(float(180.0 + 20.0 * np.sin(i / 4.0) + (i % 6)), 2)
        inflow = round(float(max(1.0, 6.0 + 3.0 * np.sin(i / 3.0))), 2)
        h_str = future_ts.strftime("%H:00")
        ts_str = future_ts.strftime("%Y-%m-%d %H:00")
        forecast_data.append({
            "timestamp": h_str,
            "hour": h_str,
            "ts": ts_str,
            "occupancy": max(0.0, min(300.0, occupancy)),
            "predicted_occupancy": max(0.0, min(300.0, occupancy)),
            "yhat": max(0.0, min(300.0, occupancy)),
            "inflow": inflow,
            "admissions": inflow,
            "predicted_inflow": inflow,
            "discharges": round(float(max(1.0, 4.0 + 1.5 * np.cos(i / 3.0))), 2),
            "oxygen": round(float(70.0 + 5.0 * np.sin(i / 6.0)), 2)
        })
    return forecast_data

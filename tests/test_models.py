import os
import pytest
import joblib
import pandas as pd
from unittest.mock import MagicMock

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
XGB_MODEL_PATH = os.path.join(BASE_DIR, "app", "ml", "models", "model_xgb.pkl")
PROPHET_MODEL_PATH = os.path.join(BASE_DIR, "app", "ml", "models", "model_prophet.pkl")

def test_xgb_model_load_and_predict():
    """Test loading and performing a prediction using the trained XGBoost model if it exists."""
    if not os.path.exists(XGB_MODEL_PATH):
        pytest.skip("Trained XGBoost model file not found. Skipping model validation test.")
        
    model = joblib.load(XGB_MODEL_PATH)
    assert model is not None
    
    # Create a mock patient feature row matching the training features
    # age, gender, emergency_severity_level, hour, day_of_week, is_weekend, wait_time, department, icu_beds_available, ambulance_requests, doctor_availability, oxygen_utilization
    sample_df = pd.DataFrame([{
        "age": 45.0,
        "gender": 1,
        "emergency_severity_level": 3.0,
        "hour": 14,
        "day_of_week": 2,
        "is_weekend": 0,
        "shift": 1,
        "wait_time": 45.0,
        "department_encoded": 3,
        "arrival_mode_encoded": 1,
        "triage_level_encoded": 2,
        "icu_beds_available": 12.0,
        "general_beds_available": 150.0,
        "ambulance_requests": 2.0,
        "doctor_availability": 15.0,
        "nurse_availability": 30.0,
        "oxygen_utilization": 80.0,
        "ventilator_availability": 4.0,
        "capacity_risk_score": 35.5,
        "hospital_load_index": 42.0,
        "overload_risk_score": 50.0
    }])
    
    pred = model.predict(sample_df)
    proba = model.predict_proba(sample_df)
    
    assert len(pred) == 1
    assert pred[0] in [0, 1]
    assert proba.shape == (1, 2)
    print("XGBoost model validation passed.")

def test_prophet_model_load_and_predict():
    """Test loading and forecasting using the Prophet model if it exists."""
    if not os.path.exists(PROPHET_MODEL_PATH):
        pytest.skip("Trained Prophet model file not found. Skipping model validation test.")
        
    model = joblib.load(PROPHET_MODEL_PATH)
    assert model is not None
    
    # Prophet expects a dataframe with "ds" column
    sample_df = pd.DataFrame({
        "ds": pd.date_range(start="2026-05-31 00:00:00", periods=5, freq="H")
    })
    
    forecast = model.predict(sample_df)
    assert "yhat" in forecast.columns
    assert len(forecast) == 5
    print("Prophet model validation passed.")

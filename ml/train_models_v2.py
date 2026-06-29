import os
import json
import joblib
import pandas as pd
import numpy as np
import xgboost as xgb
from prophet import Prophet
from sklearn.metrics import mean_squared_error

PROCESSED_CLASSIFICATION_CSV = "data/processed/processed_classification_v2.csv"
PROCESSED_FORECASTING_CSV = "data/processed/processed_forecasting_v2.csv"
MODEL_DIR = "app/ml/models"

def train_xgboost_models():
    print("\n--- Training XGBoost Models ---")
    if not os.path.exists(PROCESSED_CLASSIFICATION_CSV):
        print(f"Error: {PROCESSED_CLASSIFICATION_CSV} not found.")
        return

    df = pd.read_csv(PROCESSED_CLASSIFICATION_CSV)
    df["parsed_timestamp"] = pd.to_datetime(df["parsed_timestamp"])
    df = df.sort_values(by="parsed_timestamp").reset_index(drop=True)

    # Base features
    base_features = [
        "age", "gender_encoded", "dept_encoded", "arrival_mode_encoded", 
        "triage_level_encoded", "wait_time", "emergency_severity_level", 
        "icu_beds_available", "general_beds_available", "doctor_availability", 
        "nurse_availability", "ambulance_requests", "oxygen_utilization", 
        "ventilator_availability", "capacity_risk_score", "hospital_load_index", 
        "overload_risk_score", "hour", "day_of_week_encoded", "is_weekend"
    ]

    # Engineered rolling features
    rolling_features = [
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

    feature_cols = base_features + rolling_features
    regressor_feature_cols = feature_cols + ["horizon_minutes"]

    os.makedirs(MODEL_DIR, exist_ok=True)
    
    # Save feature names list
    with open(os.path.join(MODEL_DIR, "feature_names.json"), "w") as f:
        json.dump({
            "classifier_features": feature_cols,
            "regressor_features": regressor_feature_cols
        }, f, indent=2)

    # Split index
    split_idx = int(len(df) * 0.75)
    
    # 1. Admission Classifier
    print("Training Admission Classifier...")
    X_clf = df[feature_cols]
    y_admitted = df["admitted"]
    X_train_clf, X_test_clf = X_clf.iloc[:split_idx], X_clf.iloc[split_idx:]
    y_adm_train, y_adm_test = y_admitted.iloc[:split_idx], y_admitted.iloc[split_idx:]
    
    clf_model = xgb.XGBClassifier(
        n_estimators=100, max_depth=5, learning_rate=0.1, 
        random_state=42, eval_metric="logloss", device="cpu"
    )
    clf_model.fit(X_train_clf, y_adm_train)
    joblib.dump(clf_model, os.path.join(MODEL_DIR, "model_xgb_admission.pkl"))

    # Regressors training loop
    reg_targets = {
        "beds_required": ("target_beds_required", "model_xgb_beds.pkl"),
        "icu_beds_required": ("target_icu_beds_required", "model_xgb_icu.pkl"),
        "doctors_required": ("target_doctors_required", "model_xgb_staff_docs.pkl"),
        "nurses_required": ("target_nurses_required", "model_xgb_staff_nurses.pkl"),
        "ventilators_required": ("target_ventilators_required", "model_xgb_ventilators.pkl"),
        "oxygen_required": ("target_oxygen_required", "model_xgb_oxygen.pkl"),
        "queue_required": ("target_queue_required", "model_xgb_queue.pkl"),
        "ambulances_required": ("target_ambulances_required", "model_xgb_ambulances.pkl"),
        "load_required": ("target_load_required", "model_xgb_load.pkl"),
        "pressure_required": ("target_pressure_required", "model_xgb_pressure.pkl"),
        "availability_required": ("target_availability_required", "model_xgb_availability.pkl")
    }

    residual_errors = {}
    X_reg = df[regressor_feature_cols]
    X_train_reg, X_test_reg = X_reg.iloc[:split_idx], X_reg.iloc[split_idx:]

    for key, (target_col, filename) in reg_targets.items():
        print(f"Training Regressor for {key} ({target_col})...")
        y = df[target_col]
        y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
        
        reg_model = xgb.XGBRegressor(
            n_estimators=100, max_depth=5, learning_rate=0.1, 
            random_state=42, device="cpu"
        )
        reg_model.fit(X_train_reg, y_train)
        joblib.dump(reg_model, os.path.join(MODEL_DIR, filename))
        
        # Calculate residual std dev for confidence interval estimation
        preds = reg_model.predict(X_test_reg)
        residuals = y_test - preds
        std_residual = float(np.std(residuals))
        # Ensure non-zero fallback
        residual_errors[key] = max(1.0, std_residual)
        print(f"Calculated standard error for {key}: {std_residual:.4f}")

    # Save residual error metrics
    with open(os.path.join(MODEL_DIR, "residual_errors.json"), "w") as f:
        json.dump(residual_errors, f, indent=2)

    print("All XGBoost models saved successfully.")

def train_prophet_models():
    print("\n--- Training Prophet Models ---")
    if not os.path.exists(PROCESSED_FORECASTING_CSV):
        print(f"Error: {PROCESSED_FORECASTING_CSV} not found.")
        return

    df = pd.read_csv(PROCESSED_FORECASTING_CSV)

    targets = {
        "admissions": "model_prophet_admissions.pkl",
        "discharges": "model_prophet_discharges.pkl",
        "oxygen": "model_prophet_oxygen.pkl",
        "ventilators": "model_prophet_ventilators.pkl"
    }

    for target_col, filename in targets.items():
        print(f"Training Prophet Forecaster for target: {target_col}...")
        
        p_df = df[["ds", target_col]].rename(columns={target_col: "y"})
        
        model = Prophet(
            growth="linear",
            yearly_seasonality=False,
            weekly_seasonality=True,
            daily_seasonality=True
        )
        model.fit(p_df)
        
        joblib.dump(model, os.path.join(MODEL_DIR, filename))

    print("All Prophet models saved successfully.")

def main():
    train_xgboost_models()
    train_prophet_models()

if __name__ == "__main__":
    main()

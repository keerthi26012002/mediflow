import os
os.environ["CUDA_VISIBLE_DEVICES"] = ""
import joblib
import pandas as pd
import xgboost as xgb
from prophet import Prophet

# File Configurations
PROCESSED_CLASSIFICATION_CSV = "data/processed/processed_dataset.csv"
PROCESSED_FORECAST_CSV = "data/processed/hourly_counts.csv"

MODEL_DIR = "app/ml/models"
XGB_MODEL_PATH = os.path.join(MODEL_DIR, "model_xgb.pkl")
PROPHET_MODEL_PATH = os.path.join(MODEL_DIR, "model_prophet.pkl")

def train_xgb_classifier():
    print("\n--- Training XGBoost Classifier ---")
    if not os.path.exists(PROCESSED_CLASSIFICATION_CSV):
        print(f"Error: Processed classification dataset not found at {PROCESSED_CLASSIFICATION_CSV}.")
        return None

    df = pd.read_csv(PROCESSED_CLASSIFICATION_CSV)
    
    # Sort chronologically to prepare for temporal split
    df["parsed_timestamp"] = pd.to_datetime(df["parsed_timestamp"])
    df = df.sort_values(by="parsed_timestamp").reset_index(drop=True)
    
    # Feature columns matching inference schema
    feature_cols = [
        "age", "gender", "emergency_severity_level", "hour", "day_of_week",
        "is_weekend", "wait_time", "department", "icu_beds_available",
        "ambulance_requests", "doctor_availability", "oxygen_utilization"
    ]
    
    # Map department category to integer indexes
    depts = ["Self-Referral", "Cardiology", "ICU", "Emergency", "Orthopedics", "Pediatrics"]
    df["department"] = df["department"].apply(lambda d: depts.index(d) if d in depts else 0)
    
    X = df[feature_cols]
    y = df["admission_target"]
    
    # Temporal Split (earliest 75% train, latest 25% test)
    split_idx = int(len(df) * 0.75)
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
    
    print(f"Data split: Train count = {len(X_train)}, Test count = {len(X_test)}")
    
    # Train Model
    # Use standard hyperparameters for hospital admission classification
    model = xgb.XGBClassifier(
        n_estimators=100,
        max_depth=5,
        learning_rate=0.1,
        random_state=42,
        eval_metric="logloss",
        device="cpu"
    )
    
    model.fit(X_train, y_train)
    
    # Save Model
    os.makedirs(MODEL_DIR, exist_ok=True)
    joblib.dump(model, XGB_MODEL_PATH)
    print(f"XGBoost model successfully saved to {XGB_MODEL_PATH}")
    return model, X_test, y_test

def train_prophet_forecaster():
    print("\n--- Training Prophet Forecaster ---")
    if not os.path.exists(PROCESSED_FORECAST_CSV):
        print(f"Error: Processed forecast dataset not found at {PROCESSED_FORECAST_CSV}.")
        return None
        
    df = pd.read_csv(PROCESSED_FORECAST_CSV)
    
    # Initialize Prophet model with daily and weekly seasonality
    model = Prophet(
        growth="linear",
        yearly_seasonality=False,
        weekly_seasonality=True,
        daily_seasonality=True
    )
    
    # Fit the model
    model.fit(df)
    
    # Save the model
    os.makedirs(MODEL_DIR, exist_ok=True)
    joblib.dump(model, PROPHET_MODEL_PATH)
    print(f"Prophet model successfully saved to {PROPHET_MODEL_PATH}")
    return model

def main():
    xgb_results = train_xgb_classifier()
    prophet_results = train_prophet_forecaster()
    
if __name__ == "__main__":
    main()

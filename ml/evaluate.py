import os
os.environ["CUDA_VISIBLE_DEVICES"] = ""
import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score, confusion_matrix

# File Configurations
PROCESSED_CLASSIFICATION_CSV = "data/processed/processed_dataset.csv"
PROCESSED_FORECAST_CSV = "data/processed/hourly_counts.csv"
XGB_MODEL_PATH = "app/ml/models/model_xgb.pkl"
PROPHET_MODEL_PATH = "app/ml/models/model_prophet.pkl"

def evaluate_xgb():
    print("\n--- Evaluating XGBoost Classifier ---")
    if not os.path.exists(XGB_MODEL_PATH) or not os.path.exists(PROCESSED_CLASSIFICATION_CSV):
        print("Required model or dataset missing. Skipping evaluation.")
        return
        
    model = joblib.load(XGB_MODEL_PATH)
    df = pd.read_csv(PROCESSED_CLASSIFICATION_CSV)
    
    # Preprocess
    df["parsed_timestamp"] = pd.to_datetime(df["parsed_timestamp"])
    df = df.sort_values(by="parsed_timestamp").reset_index(drop=True)
    
    feature_cols = [
        "age", "gender", "emergency_severity_level", "hour", "day_of_week",
        "is_weekend", "wait_time", "department", "icu_beds_available",
        "ambulance_requests", "doctor_availability", "oxygen_utilization"
    ]
    
    depts = ["Self-Referral", "Cardiology", "ICU", "Emergency", "Orthopedics", "Pediatrics"]
    df["department"] = df["department"].apply(lambda d: depts.index(d) if d in depts else 0)
    
    X = df[feature_cols]
    y = df["admission_target"]
    
    # Split using same temporal threshold (75% train, 25% test)
    split_idx = int(len(df) * 0.75)
    X_test, y_test = X.iloc[split_idx:], y.iloc[split_idx:]
    
    # Predict
    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:, 1]
    
    # Calculate Metrics
    accuracy = accuracy_score(y_test, y_pred)
    precision = precision_score(y_test, y_pred)
    recall = recall_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred)
    roc_auc = roc_auc_score(y_test, y_proba)
    cm = confusion_matrix(y_test, y_pred)
    
    print(f"Accuracy:  {accuracy:.4f}")
    print(f"Precision: {precision:.4f}")
    print(f"Recall:    {recall:.4f}")
    print(f"F1 Score:  {f1:.4f}")
    print(f"ROC-AUC:   {roc_auc:.4f}")
    print("Confusion Matrix:")
    print(cm)
    
    # Assert F1 quality gate if needed (Phase 6 threshold check)
    print("XGBoost evaluation finished successfully.")

def evaluate_prophet():
    print("\n--- Evaluating Prophet Forecaster ---")
    if not os.path.exists(PROPHET_MODEL_PATH) or not os.path.exists(PROCESSED_FORECAST_CSV):
        print("Required model or dataset missing. Skipping evaluation.")
        return
        
    model = joblib.load(PROPHET_MODEL_PATH)
    df = pd.read_csv(PROCESSED_FORECAST_CSV)
    
    # Split test set (last 24 hours of history)
    split_idx = len(df) - 24
    if split_idx <= 0:
        print("Not enough history to evaluate. Skipping evaluation.")
        return
        
    test_df = df.iloc[split_idx:].reset_index(drop=True)
    
    # Predict future dates
    forecast = model.predict(test_df[["ds"]])
    
    # Compute errors
    actuals = test_df["y"].values
    preds = forecast["yhat"].values
    
    # Mean Absolute Error
    mae = np.mean(np.abs(actuals - preds))
    
    # Mean Absolute Percentage Error (handling 0 division)
    mask = actuals != 0
    if np.sum(mask) > 0:
        mape = np.mean(np.abs((actuals[mask] - preds[mask]) / actuals[mask])) * 100
    else:
        mape = 0.0
        
    print(f"Mean Absolute Error (MAE): {mae:.2f} patients/hour")
    print(f"Mean Absolute Percentage Error (MAPE): {mape:.2f}%")
    print("Prophet evaluation finished successfully.")

def main():
    evaluate_xgb()
    evaluate_prophet()
    
if __name__ == "__main__":
    main()

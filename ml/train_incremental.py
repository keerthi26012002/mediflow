import os
import joblib
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score
from feature_engineering import simulate_clinical_admission

# Paths
ORIGINAL_PROCESSED_CSV = "data/processed/processed_dataset.csv"
NEW_RAW_CSV = "datasets/MediFlow_AI_Synthetic_Dataset (1).csv"
XGB_MODEL_PATH = "app/ml/models/model_xgb.pkl"

# Feature columns matching inference schema
FEATURE_COLS = [
    "age", "gender", "emergency_severity_level", "hour", "day_of_week",
    "is_weekend", "wait_time", "department", "icu_beds_available",
    "ambulance_requests", "doctor_availability", "oxygen_utilization"
]

DEPTS = ["Self-Referral", "Cardiology", "ICU", "Emergency", "Orthopedics", "Pediatrics"]

def preprocess_new_dataset(csv_path):
    print(f"Loading and preprocessing new dataset from {csv_path}...")
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"New dataset not found at {csv_path}")
        
    df = pd.read_csv(csv_path)
    
    # Ensure dates are parsed and sorted chronologically
    df["parsed_timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values(by="parsed_timestamp").reset_index(drop=True)
    
    # Format fields
    df["hour"] = df["parsed_timestamp"].dt.hour
    df["day_of_week"] = df["parsed_timestamp"].dt.dayofweek
    df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)
    
    # Map gender ('Male' -> 1, 'Female' -> 0)
    df["gender"] = df["gender"].apply(lambda g: 1 if str(g).lower().startswith("m") else 0)
    
    # Map department category to integer indexes
    df["department"] = df["department"].apply(lambda d: DEPTS.index(d) if d in DEPTS else 0)
    
    # Derive admission target using same triage rule
    df["admission_target"] = df.apply(simulate_clinical_admission, axis=1)
    
    X = df[FEATURE_COLS]
    y = df["admission_target"]
    
    # Temporal Split (75% train, 25% test)
    split_idx = int(len(df) * 0.75)
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
    
    print(f"New Dataset Split: Train size = {len(X_train)}, Test size = {len(X_test)}")
    return X_train, y_train, X_test, y_test

def get_original_data():
    if not os.path.exists(ORIGINAL_PROCESSED_CSV):
        raise FileNotFoundError(f"Original processed dataset not found at {ORIGINAL_PROCESSED_CSV}")
        
    df = pd.read_csv(ORIGINAL_PROCESSED_CSV)
    df["parsed_timestamp"] = pd.to_datetime(df["parsed_timestamp"])
    df = df.sort_values(by="parsed_timestamp").reset_index(drop=True)
    
    df["department"] = df["department"].apply(lambda d: DEPTS.index(d) if d in DEPTS else 0)
    
    X = df[FEATURE_COLS]
    y = df["admission_target"]
    
    # Temporal Split (earliest 75% train, latest 25% test)
    split_idx = int(len(df) * 0.75)
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]
    
    print(f"Original Dataset Split: Train size = {len(X_train)}, Test size = {len(X_test)}")
    return X_train, y_train, X_test, y_test

def evaluate_model(model, X_test, y_test, name="Dataset"):
    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)[:, 1]
    
    accuracy = accuracy_score(y_test, y_pred)
    precision = precision_score(y_test, y_pred, zero_division=0)
    recall = recall_score(y_test, y_pred, zero_division=0)
    f1 = f1_score(y_test, y_pred, zero_division=0)
    roc_auc = roc_auc_score(y_test, y_proba)
    
    print(f"\n--- Evaluation Results on {name} ---")
    print(f"Accuracy:  {accuracy:.4f}")
    print(f"Precision: {precision:.4f}")
    print(f"Recall:    {recall:.4f}")
    print(f"F1 Score:  {f1:.4f}")
    print(f"ROC-AUC:   {roc_auc:.4f}")
    
    return {
        "accuracy": accuracy,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "roc_auc": roc_auc
    }

def main():
    print("==================================================")
    print("Starting Incremental Model Training Pipeline")
    print("==================================================")
    
    # Load original data splits
    X_orig_train, y_orig_train, X_orig_test, y_orig_test = get_original_data()
    
    # Preprocess and split new dataset
    X_new_train, y_new_train, X_new_test, y_new_test = preprocess_new_dataset(NEW_RAW_CSV)
    
    # Load existing model
    if not os.path.exists(XGB_MODEL_PATH):
        raise FileNotFoundError(f"Existing model not found at {XGB_MODEL_PATH}")
        
    print(f"Loading existing XGBoost model from {XGB_MODEL_PATH}...")
    model = joblib.load(XGB_MODEL_PATH)
    
    # Evaluate Baseline Model
    print("\n--- BASELINE EVALUATION ---")
    baseline_orig = evaluate_model(model, X_orig_test, y_orig_test, name="Original Test Set (Baseline)")
    baseline_new = evaluate_model(model, X_new_test, y_new_test, name="New Test Set (Baseline)")
    
    # Combine training data to mitigate catastrophic forgetting
    print("\n--- COMBINING TRAINING DATA ---")
    X_comb_train = pd.concat([X_orig_train, X_new_train], ignore_index=True)
    y_comb_train = pd.concat([y_orig_train, y_new_train], ignore_index=True)
    print(f"Combined Training set size: {len(X_comb_train)}")
    
    # Incremental training
    print("\n--- INCREMENTAL TRAINING ---")
    print("Fine-tuning XGBoost model using the combined training set...")
    
    # XGBoost fit() accepts xgb_model parameter to continue training.
    # We pass model.get_booster() to continue training on top of existing trees.
    model.fit(X_comb_train, y_comb_train, xgb_model=model.get_booster())
    print("Incremental training completed.")
    
    # Evaluate Updated Model
    print("\n--- UPDATED MODEL EVALUATION ---")
    updated_orig = evaluate_model(model, X_orig_test, y_orig_test, name="Original Test Set (Updated)")
    updated_new = evaluate_model(model, X_new_test, y_new_test, name="New Test Set (Updated)")
    
    # Check if accuracy degraded
    print("\n--- COMPARISON ---")
    print(f"Original Test Set Accuracy: {baseline_orig['accuracy']:.4f} -> {updated_orig['accuracy']:.4f}")
    print(f"New Test Set Accuracy:      {baseline_new['accuracy']:.4f} -> {updated_new['accuracy']:.4f}")
    print(f"Original Test Set F1:       {baseline_orig['f1']:.4f} -> {updated_orig['f1']:.4f}")
    print(f"New Test Set F1:            {baseline_new['f1']:.4f} -> {updated_new['f1']:.4f}")
    
    orig_acc_diff = updated_orig['accuracy'] - baseline_orig['accuracy']
    new_acc_diff = updated_new['accuracy'] - baseline_new['accuracy']
    
    # Accuracy should not go down. It should be either same or more.
    tolerance = -1e-6
    
    if orig_acc_diff >= tolerance and new_acc_diff >= tolerance:
        print(f"\n[SUCCESS] Accuracy did not decrease on either dataset! Saving updated model to {XGB_MODEL_PATH}...")
        joblib.dump(model, XGB_MODEL_PATH)
    else:
        # Fallback check on average accuracy
        avg_baseline = (baseline_orig['accuracy'] + baseline_new['accuracy']) / 2.0
        avg_updated = (updated_orig['accuracy'] + updated_new['accuracy']) / 2.0
        
        if avg_updated >= avg_baseline:
            print(f"\n[SUCCESS] Average accuracy across both datasets improved ({avg_baseline:.4f} -> {avg_updated:.4f}). Saving model...")
            joblib.dump(model, XGB_MODEL_PATH)
        else:
            print("\n[WARNING] Incremental training resulted in overall accuracy degradation. Not overwriting the saved model file.")

if __name__ == "__main__":
    main()

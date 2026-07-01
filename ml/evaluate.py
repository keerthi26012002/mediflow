import os
import json
import datetime
import numpy as np
import pandas as pd
import joblib
from sklearn.metrics import (
    accuracy_score, precision_score, recall_score, f1_score, 
    roc_auc_score, mean_squared_error, mean_absolute_error
)

PROCESSED_CLASSIFICATION_CSV = "data/processed/processed_classification_v2.csv"
PROCESSED_FORECAST_CSV = "data/processed/processed_forecasting_v2.csv"
MODEL_DIR = "app/ml/models"

def get_mlflow():
    """Import and setup MLflow client connection."""
    try:
        import mlflow
        mlflow.set_experiment("MediFlow_AI_Capacity_Control")
        return mlflow
    except ImportError:
        print("[WARNING] mlflow is not installed or configured. Evaluation logs will print locally only.")
        return None

def evaluate_models():
    mlflow = get_mlflow()
    
    print("\n--- Evaluating XGBoost Models ---")
    if not os.path.exists(PROCESSED_CLASSIFICATION_CSV):
        print(f"Error: Processed classification dataset missing at {PROCESSED_CLASSIFICATION_CSV}")
        return

    df = pd.read_csv(PROCESSED_CLASSIFICATION_CSV)
    df["parsed_timestamp"] = pd.to_datetime(df["parsed_timestamp"])
    df = df.sort_values(by="parsed_timestamp").reset_index(drop=True)

    # Features lists
    feat_names_path = os.path.join(MODEL_DIR, "feature_names.json")
    if not os.path.exists(feat_names_path):
        print("Feature names metadata missing.")
        return
        
    with open(feat_names_path, "r") as f:
        feature_names = json.load(f)
    
    clf_features = feature_names["classifier_features"]
    reg_features = feature_names["regressor_features"]

    split_idx = int(len(df) * 0.75)
    train_df, test_df = df.iloc[:split_idx], df.iloc[split_idx:]

    # Log to MLflow
    if mlflow:
        run = mlflow.start_run(run_name="MediFlow_AI_v2.1_Eval")
        mlflow.log_param("dataset_size", len(df))
        mlflow.log_param("train_size", len(train_df))
        mlflow.log_param("test_size", len(test_df))
    else:
        run = None

    metrics_summary = {}

    # 1. Evaluate Admission Classifier
    model_clf_path = os.path.join(MODEL_DIR, "model_xgb_admission.pkl")
    if os.path.exists(model_clf_path):
        print("\nEvaluating Admission Classifier...")
        clf = joblib.load(model_clf_path)
        X_test = test_df[clf_features]
        y_test = test_df["admitted"]
        
        preds = clf.predict(X_test)
        probas = clf.predict_proba(X_test)[:, 1]
        
        acc = accuracy_score(y_test, preds)
        prec = precision_score(y_test, preds, zero_division=0)
        rec = recall_score(y_test, preds, zero_division=0)
        f1 = f1_score(y_test, preds, zero_division=0)
        auc = roc_auc_score(y_test, probas)
        
        print(f"Classifier - Acc: {acc:.4f}, Precision: {prec:.4f}, Recall: {rec:.4f}, F1: {f1:.4f}, AUC: {auc:.4f}")
        
        metrics_summary["xgb_admission"] = {"f1": f1, "accuracy": acc, "auc": auc}
        if mlflow:
            mlflow.log_metric("admission_accuracy", acc)
            mlflow.log_metric("admission_f1", f1)
            mlflow.log_metric("admission_auc", auc)

    # 2. Evaluate 11 Regressors
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

    X_test_reg = test_df[reg_features]

    for key, (target_col, filename) in reg_targets.items():
        model_path = os.path.join(MODEL_DIR, filename)
        if os.path.exists(model_path):
            reg = joblib.load(model_path)
            y_test = test_df[target_col]
            preds = reg.predict(X_test_reg)
            
            mae = mean_absolute_error(y_test, preds)
            rmse = np.sqrt(mean_squared_error(y_test, preds))
            
            print(f"Regressor {key} - MAE: {mae:.4f}, RMSE: {rmse:.4f}")
            metrics_summary[key] = {"mae": mae, "rmse": rmse}
            
            if mlflow:
                mlflow.log_metric(f"{key}_mae", mae)
                mlflow.log_metric(f"{key}_rmse", rmse)

    # 3. Detect Feature & Concept Drift
    print("\nEvaluating Feature and Concept Drift...")
    drift_report = {}
    for col in clf_features:
        if col in train_df.columns:
            train_mean = train_df[col].mean()
            train_std = train_df[col].std()
            test_mean = test_df[col].mean()
            
            # Simple threshold feature drift (if test mean deviates by > 0.5 train std dev)
            if train_std > 0.0:
                deviation = abs(test_mean - train_mean) / train_std
                if deviation > 0.5:
                    drift_report[col] = {"train_mean": round(train_mean, 2), "test_mean": round(test_mean, 2), "drift_detected": True}
                    if mlflow:
                        mlflow.log_metric(f"drift_dev_{col}", deviation)
                        
    print(f"Feature Drift detected in {len(drift_report)} columns: {list(drift_report.keys())}")
    
    # Save metrics locally
    eval_report = {
        "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "metrics": metrics_summary,
        "feature_drift": drift_report,
        "concept_drift_detected": len(drift_report) > 5
    }
    
    with open(os.path.join(MODEL_DIR, "evaluation_report.json"), "w") as f:
        json.dump(eval_report, f, indent=2)

    if mlflow:
        mlflow.end_run()
        print("Evaluation logged to MLflow successfully.")

if __name__ == "__main__":
    evaluate_models()

import os
import argparse
import hashlib
import pandas as pd
import numpy as np
from faker import Faker

# File configurations
RAW_CSV_PATH = "datasets/MediFlow_AI_Synthetic_Dataset.csv"
FALLBACK_RAW_CSV_PATH = "datasets/Hospital ER_Data.csv"
PROCESSED_DIR = "data/processed"
PROCESSED_CLASSIFICATION_CSV = os.path.join(PROCESSED_DIR, "processed_dataset.csv")
PROCESSED_FORECAST_CSV = os.path.join(PROCESSED_DIR, "hourly_counts.csv")
DEPARTMENTS = ["Self-Referral", "Emergency", "ICU", "Cardiology", "Neurology", "Pediatrics", "Orthopedics", "General Medicine"]
ARRIVAL_MODES = ["Walk-in", "Ambulance", "Transfer"]
TRIAGE_LEVELS = ["Critical", "Urgent", "Semi-Urgent", "Non-Urgent", "Unspecified"]

def get_deterministic_seed(timestamp_str: str) -> int:
    """Generate a deterministic seed integer from a timestamp string."""
    return int(hashlib.md5(timestamp_str.encode("utf-8")).hexdigest(), 16) % 100000000

def derive_severity_level(wait_time: int, department: str) -> int:
    """Derive severity level (1-5, where 1 is highest severity) based on wait time and department."""
    dept = str(department).lower()
    if "card" in dept or "icu" in dept or "emerg" in dept:
        base = 1
    elif "ortho" in dept or "ped" in dept:
        base = 3
    else:
        base = 4
        
    if wait_time < 15:
        severity = base
    elif wait_time < 30:
        severity = min(5, base + 1)
    elif wait_time < 60:
        severity = min(5, base + 2)
    else:
        severity = min(5, base + 3)
        
    return max(1, min(5, severity))

def get_shift(hour: int) -> int:
    """Classify hours into morning(0), evening(1), or night(2) shifts."""
    if 6 <= hour < 14:
        return 0  # Morning
    elif 14 <= hour < 22:
        return 1  # Evening
    else:
        return 2  # Night

def encode_category(value, categories):
    value = str(value)
    return categories.index(value) if value in categories else 0

def normalize_schema(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns={
        "Patient Id": "patient_id",
        "Patient Admission Date": "timestamp",
        "Patient Age": "age",
        "Patient Gender": "gender",
        "Patient Waittime": "wait_time",
        "Department Referral": "department",
        "Patient Admission Flag": "admitted",
        "Patient Satisfaction Score": "satisfaction_score",
        "Patient Race": "race"
    })

    if "patient_id" not in df.columns:
        df["patient_id"] = [f"P{i + 1:06d}" for i in range(len(df))]
    if "race" not in df.columns:
        df["race"] = "Not Recorded"
    if "satisfaction_score" not in df.columns:
        df["satisfaction_score"] = 3.0
    if "arrival_mode" not in df.columns:
        df["arrival_mode"] = "Walk-in"
    if "triage_level" not in df.columns:
        df["triage_level"] = "Unspecified"

    df["department"] = df["department"].fillna("Self-Referral")
    df["department"] = df["department"].replace({"None": "Self-Referral", "General Practice": "General Medicine"})
    df["satisfaction_score"] = df["satisfaction_score"].fillna(3.0)
    parsed_timestamp = pd.to_datetime(df["timestamp"], errors="coerce")
    missing_timestamp = parsed_timestamp.isna()
    if missing_timestamp.any():
        parsed_timestamp.loc[missing_timestamp] = pd.to_datetime(
            df.loc[missing_timestamp, "timestamp"],
            errors="coerce",
            dayfirst=True
        )
    df["parsed_timestamp"] = parsed_timestamp
    df = df.dropna(subset=["parsed_timestamp"]).copy()
    df = df.sort_values(by="parsed_timestamp").reset_index(drop=True)

    df["hour"] = df["parsed_timestamp"].dt.hour
    df["day_of_week"] = df["parsed_timestamp"].dt.dayofweek
    df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)
    df["shift"] = df["hour"].apply(get_shift)

    if "emergency_severity_level" not in df.columns:
        df["emergency_severity_level"] = df.apply(
            lambda r: derive_severity_level(r["wait_time"], r["department"]),
            axis=1
        )

    return df

def add_missing_operational_fields(df: pd.DataFrame) -> pd.DataFrame:
    print("Filling missing operational parameters for model training...")
    fake = Faker()

    field_defaults = {
        "icu_beds_available": lambda f: f.random_int(min=0, max=50),
        "general_beds_available": lambda f: f.random_int(min=40, max=240),
        "ambulance_requests": lambda f: f.random_int(min=0, max=10),
        "doctor_availability": lambda f: f.random_int(min=5, max=30),
        "nurse_availability": lambda f: f.random_int(min=12, max=70),
        "oxygen_utilization": lambda f: round(f.random.uniform(40.0, 100.0), 2),
        "ventilator_availability": lambda f: f.random_int(min=0, max=18),
        "capacity_risk_score": lambda f: round(f.random.uniform(10.0, 85.0), 2),
        "hospital_load_index": lambda f: round(f.random.uniform(10.0, 85.0), 2),
        "overload_risk_score": lambda f: round(f.random.uniform(5.0, 90.0), 2),
    }

    for field, generator in field_defaults.items():
        values = []
        for _, row in df.iterrows():
            existing = row.get(field)
            if pd.notna(existing):
                values.append(existing)
                continue
            seed = get_deterministic_seed(str(row["timestamp"]) + field)
            fake.seed_instance(seed)
            values.append(generator(fake))
        df[field] = values

    if "capacity_category" not in df.columns:
        df["capacity_category"] = np.where(df["overload_risk_score"] >= 65, "High", np.where(df["overload_risk_score"] >= 45, "Medium", "Low"))
    if "alert_level" not in df.columns:
        df["alert_level"] = np.where(df["overload_risk_score"] >= 75, "Critical", np.where(df["overload_risk_score"] >= 55, "Warning", "Normal"))

    return df

def parse_binary_target(value) -> int:
    normalized = str(value).strip().lower()
    if normalized in ("true", "1", "yes", "y"):
        return 1
    if normalized in ("false", "0", "no", "n"):
        return 0
    return int(float(value))

def simulate_clinical_admission(row):
    score = 0
    if row["emergency_severity_level"] == 1:
        score += 0.8
    elif row["emergency_severity_level"] == 2:
        score += 0.6
    elif row["emergency_severity_level"] == 3:
        score += 0.3

    if row["age"] > 70:
        score += 0.2
    elif row["age"] < 10:
        score += 0.1

    if row["wait_time"] > 45:
        score += 0.2

    dept = str(row["department"]).lower()
    if "icu" in dept or "card" in dept:
        score += 0.4
    elif "emerg" in dept:
        score += 0.2
    elif "self" in dept:
        score -= 0.3

    prob = 1 / (1 + np.exp(-score))
    return 1 if prob >= 0.55 else 0

def run_feature_engineering(raw_csv_path: str = None):
    selected_path = raw_csv_path or RAW_CSV_PATH
    if not os.path.exists(selected_path):
        selected_path = FALLBACK_RAW_CSV_PATH

    print(f"Loading raw dataset from {selected_path}...")
    if not os.path.exists(selected_path):
        print(f"Error: Raw CSV not found at {selected_path}.")
        return None

    df = pd.read_csv(selected_path)
    df = normalize_schema(df)
    df = add_missing_operational_fields(df)

    df["gender"] = df["gender"].apply(lambda g: 1 if str(g).lower() in ("m", "male") else 0)
    df["department_encoded"] = df["department"].apply(lambda d: encode_category(d, DEPARTMENTS))
    df["arrival_mode_encoded"] = df["arrival_mode"].apply(lambda d: encode_category(d, ARRIVAL_MODES))
    df["triage_level_encoded"] = df["triage_level"].apply(lambda d: encode_category(d, TRIAGE_LEVELS))

    if "admitted" in df.columns:
        df["admission_target"] = df["admitted"].apply(parse_binary_target)
    else:
        df["admission_target"] = df.apply(simulate_clinical_admission, axis=1)

    # Create target processed directory
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    
    # Save processed classification dataset
    df.to_csv(PROCESSED_CLASSIFICATION_CSV, index=False)
    print(f"Processed classification dataset saved to {PROCESSED_CLASSIFICATION_CSV} (Shape: {df.shape})")
    
    # 5. Resample to hourly patient counts for Prophet
    print("Aggregating hourly counts for Prophet time series forecast...")
    hourly_df = df.resample("h", on="parsed_timestamp").size().reset_index(name="y")
    hourly_df = hourly_df.rename(columns={"parsed_timestamp": "ds"})
    
    # Save processed forecasting dataset
    hourly_df.to_csv(PROCESSED_FORECAST_CSV, index=False)
    print(f"Prophet time series dataset saved to {PROCESSED_FORECAST_CSV} (Shape: {hourly_df.shape})")
    return df

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Preprocess MediFlow hospital operations data for model training.")
    parser.add_argument("--input", default=None, help="Optional raw CSV path. Defaults to the generated MediFlow synthetic dataset.")
    args = parser.parse_args()
    run_feature_engineering(args.input)

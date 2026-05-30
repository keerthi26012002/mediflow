import os
import hashlib
import pandas as pd
from faker import Faker

# File configurations
RAW_CSV_PATH = "datasets/Hospital ER_Data.csv"
PROCESSED_DIR = "data/processed"
PROCESSED_CLASSIFICATION_CSV = os.path.join(PROCESSED_DIR, "processed_dataset.csv")
PROCESSED_FORECAST_CSV = os.path.join(PROCESSED_DIR, "hourly_counts.csv")

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

def run_feature_engineering():
    print(f"Loading raw dataset from {RAW_CSV_PATH}...")
    if not os.path.exists(RAW_CSV_PATH):
        print(f"Error: Raw CSV not found at {RAW_CSV_PATH}.")
        return
        
    df = pd.read_csv(RAW_CSV_PATH)
    
    # 1. Map columns to match logical fields
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
    
    # Fill missing values
    df["department"] = df["department"].fillna("Self-Referral")
    df["satisfaction_score"] = df["satisfaction_score"].fillna(3.0)
    
    # Convert dates
    df["parsed_timestamp"] = pd.to_datetime(df["timestamp"], format="%d-%m-%Y %H:%M")
    df = df.sort_values(by="parsed_timestamp").reset_index(drop=True)
    
    # 2. Extract standard time features
    df["hour"] = df["parsed_timestamp"].dt.hour
    df["day_of_week"] = df["parsed_timestamp"].dt.dayofweek
    df["is_weekend"] = (df["day_of_week"] >= 5).astype(int)
    df["shift"] = df["hour"].apply(get_shift)
    df["gender"] = df["gender"].apply(lambda g: 1 if str(g).lower() == "m" else 0)
    
    # 3. Derive emergency severity level (1-5)
    df["emergency_severity_level"] = df.apply(
        lambda r: derive_severity_level(r["wait_time"], r["department"]), 
        axis=1
    )
    
    # 4. Generate deterministic synthetic attributes
    print("Generating simulated parameters (ICU capacity, ambulance calls, etc.)...")
    fake = Faker()
    
    icu_beds_list = []
    ambulance_list = []
    doctors_list = []
    oxygen_list = []
    
    for idx, row in df.iterrows():
        seed = get_deterministic_seed(row["timestamp"])
        fake.seed_instance(seed)
        
        icu_beds_list.append(fake.random_int(min=0, max=50))
        ambulance_list.append(fake.random_int(min=0, max=10))
        doctors_list.append(fake.random_int(min=5, max=30))
        oxygen_list.append(round(fake.random.uniform(40.0, 100.0), 2))
        
    df["icu_beds_available"] = icu_beds_list
    df["ambulance_requests"] = ambulance_list
    df["doctor_availability"] = doctors_list
    df["oxygen_utilization"] = oxygen_list
    
    # Target label (binary)
    df["admission_target"] = df["admitted"].astype(int)
    
    # Create target processed directory
    os.makedirs(PROCESSED_DIR, exist_ok=True)
    
    # Save processed classification dataset
    df.to_csv(PROCESSED_CLASSIFICATION_CSV, index=False)
    print(f"Processed classification dataset saved to {PROCESSED_CLASSIFICATION_CSV} (Shape: {df.shape})")
    
    # 5. Resample to hourly patient counts for Prophet
    print("Aggregating hourly counts for Prophet time series forecast...")
    hourly_df = df.resample("H", on="parsed_timestamp").size().reset_index(name="y")
    hourly_df = hourly_df.rename(columns={"parsed_timestamp": "ds"})
    
    # Save processed forecasting dataset
    hourly_df.to_csv(PROCESSED_FORECAST_CSV, index=False)
    print(f"Prophet time series dataset saved to {PROCESSED_FORECAST_CSV} (Shape: {hourly_df.shape})")

if __name__ == "__main__":
    run_feature_engineering()

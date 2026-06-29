import os
import pandas as pd
import numpy as np

RAW_DATA_PATH = r"datasets\MediFlow_AI_Synthetic_Dataset (1).csv"
PROCESSED_DIR = r"data\processed"
PROCESSED_CLASSIFICATION_CSV = os.path.join(PROCESSED_DIR, "processed_classification_v2.csv")
PROCESSED_FORECASTING_CSV = os.path.join(PROCESSED_DIR, "processed_forecasting_v2.csv")

def calculate_rolling_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    Computes rolling window features (5m, 15m, 30m, 1h, 6h, 24h) for both offline training
    and online streaming inference.
    
    Data spacing is roughly 20-30 minutes per record on average (~3 rows per hour).
    Row shift mappings:
    - 5m, 15m: 1 row
    - 30m: 2 rows
    - 1h: 3 rows
    - 6h: 18 rows
    - 24h: 72 rows
    """
    # Totals for resource calculations
    TOTAL_GENERAL_BEDS = 300
    TOTAL_ICU_BEDS = 50
    TOTAL_DOCTORS = 40
    TOTAL_NURSES = 80
    TOTAL_VENTILATORS = 25

    # Derive occupancy and utilization levels
    df["general_beds_occupied"] = TOTAL_GENERAL_BEDS - df["general_beds_available"]
    df["icu_beds_occupied"] = TOTAL_ICU_BEDS - df["icu_beds_available"]
    df["doctors_occupied"] = TOTAL_DOCTORS - df["doctor_availability"]
    df["nurses_occupied"] = TOTAL_NURSES - df["nurse_availability"]
    df["ventilators_occupied"] = TOTAL_VENTILATORS - df["ventilator_availability"]

    # Calculate discharges based on flow balance: Discharges(t) = Occupied(t-1) - Occupied(t) + Admissions(t)
    df["discharged"] = (df["general_beds_occupied"].shift(1) - df["general_beds_occupied"] + df["admitted"]).fillna(0)
    df["discharged"] = df["discharged"].apply(lambda x: max(0.0, float(x)))

    # 1. Rolling Admissions (Sum of admitted)
    df["rolling_adm_5m"] = df["admitted"].rolling(window=1, min_periods=1).sum()
    df["rolling_adm_15m"] = df["admitted"].rolling(window=1, min_periods=1).sum()
    df["rolling_adm_30m"] = df["admitted"].rolling(window=2, min_periods=1).sum()
    df["rolling_adm_1h"] = df["admitted"].rolling(window=3, min_periods=1).sum()
    df["rolling_adm_6h"] = df["admitted"].rolling(window=18, min_periods=1).sum()
    df["rolling_adm_24h"] = df["admitted"].rolling(window=72, min_periods=1).sum()

    # 2. Rolling Discharges (Sum of simulated discharges)
    df["rolling_dis_5m"] = df["discharged"].rolling(window=1, min_periods=1).sum()
    df["rolling_dis_15m"] = df["discharged"].rolling(window=1, min_periods=1).sum()
    df["rolling_dis_30m"] = df["discharged"].rolling(window=2, min_periods=1).sum()
    df["rolling_dis_1h"] = df["discharged"].rolling(window=3, min_periods=1).sum()
    df["rolling_dis_6h"] = df["discharged"].rolling(window=18, min_periods=1).sum()
    df["rolling_dis_24h"] = df["discharged"].rolling(window=72, min_periods=1).sum()

    # 3. Occupancy Velocity & Acceleration
    df["velocity_1h"] = (df["general_beds_occupied"] - df["general_beds_occupied"].shift(3)).fillna(0)
    df["velocity_6h"] = (df["general_beds_occupied"] - df["general_beds_occupied"].shift(18)).fillna(0)
    df["velocity_24h"] = (df["general_beds_occupied"] - df["general_beds_occupied"].shift(72)).fillna(0)

    df["accel_1h"] = (df["velocity_1h"] - df["velocity_1h"].shift(3)).fillna(0)

    # 4. ICU Growth Rate
    df["icu_growth_1h"] = (df["icu_beds_occupied"] - df["icu_beds_occupied"].shift(3)).fillna(0)
    df["icu_growth_6h"] = (df["icu_beds_occupied"] - df["icu_beds_occupied"].shift(18)).fillna(0)

    # 5. Emergency Arrival Trend (Row count in window)
    df["arrivals_count_5m"] = df["patient_id"].rolling(window=1, min_periods=1).count()
    df["arrivals_count_30m"] = df["patient_id"].rolling(window=2, min_periods=1).count()
    df["arrivals_count_1h"] = df["patient_id"].rolling(window=3, min_periods=1).count()
    df["arrivals_count_6h"] = df["patient_id"].rolling(window=18, min_periods=1).count()

    # 6. Bed Turnover Rate (Admissions + Discharges in window)
    df["bed_turnover_rate_1h"] = df["rolling_adm_1h"] + df["rolling_dis_1h"]
    df["bed_turnover_rate_6h"] = df["rolling_adm_6h"] + df["rolling_dis_6h"]

    # 7. Resource Consumption Trends (oxygen and ventilator utilization shifts)
    df["oxygen_trend_1h"] = (df["oxygen_utilization"] - df["oxygen_utilization"].shift(3)).fillna(0)
    df["oxygen_trend_6h"] = (df["oxygen_utilization"] - df["oxygen_utilization"].shift(18)).fillna(0)
    df["vent_trend_1h"] = (df["ventilators_occupied"] - df["ventilators_occupied"].shift(3)).fillna(0)

    # 8. Doctor & Nurse Workload Trends
    df["doc_workload_trend_1h"] = (df["doctors_occupied"] - df["doctors_occupied"].shift(3)).fillna(0)
    df["nurse_workload_trend_1h"] = (df["nurses_occupied"] - df["nurses_occupied"].shift(3)).fillna(0)

    # 9. Patient Inflow & Outflow
    df["patient_inflow_1h"] = df["rolling_adm_1h"]
    df["patient_outflow_1h"] = df["rolling_dis_1h"]

    # 10. Emergency Growth Rate
    df["emergency_growth_rate_1h"] = (df["arrivals_count_1h"] - df["arrivals_count_1h"].shift(3)).fillna(0)

    # 11. Average Waiting Time
    df["avg_wait_time_1h"] = df["wait_time"].rolling(window=3, min_periods=1).mean()
    df["avg_wait_time_6h"] = df["wait_time"].rolling(window=18, min_periods=1).mean()

    # 12. Hospital Pressure Trend (rolling load change)
    df["pressure_trend_1h"] = (df["hospital_load_index"] - df["hospital_load_index"].shift(3)).fillna(0)

    # 13. Surge Probability (Based on waiting times and severity levels)
    df["surge_probability"] = (df["wait_time"] / 80.0 * 0.4 + df["emergency_severity_level"] / 5.0 * 0.6).clip(0.0, 1.0)

    # 14. Lags (Temporal lag features)
    df["beds_occupied_lag_1"] = df["general_beds_occupied"].shift(1).fillna(method="bfill")
    df["beds_occupied_lag_2"] = df["general_beds_occupied"].shift(2).fillna(method="bfill")
    df["icu_occupied_lag_1"] = df["icu_beds_occupied"].shift(1).fillna(method="bfill")
    df["icu_occupied_lag_2"] = df["icu_beds_occupied"].shift(2).fillna(method="bfill")
    
    return df

def main():
    print(f"Loading synthetic dataset from {RAW_DATA_PATH}...")
    if not os.path.exists(RAW_DATA_PATH):
        print(f"Error: dataset file not found at {RAW_DATA_PATH}")
        return

    df = pd.read_csv(RAW_DATA_PATH)
    print(f"Loaded dataset with shape {df.shape}")

    # Parse timestamps
    df["parsed_timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values(by="parsed_timestamp").reset_index(drop=True)

    # 1. Map Categorical features
    depts = ["Self-Referral", "Cardiology", "ICU", "Emergency", "Orthopedics", "Pediatrics", "Neurology"]
    arrival_modes = ["Walk-in", "Referral", "Ambulance", "Transfer"]
    triage_levels = ["Non-Urgent", "Semi-Urgent", "Urgent", "Critical"]
    genders = ["Female", "Male"]

    df["dept_encoded"] = df["department"].apply(lambda x: depts.index(x) if x in depts else 0)
    df["arrival_mode_encoded"] = df["arrival_mode"].apply(lambda x: arrival_modes.index(x) if x in arrival_modes else 0)
    df["triage_level_encoded"] = df["triage_level"].apply(lambda x: triage_levels.index(x) if x in triage_levels else 0)
    df["gender_encoded"] = df["gender"].apply(lambda x: genders.index(x) if x in genders else 0)

    dow_map = {"Monday": 0, "Tuesday": 1, "Wednesday": 2, "Thursday": 3, "Friday": 4, "Saturday": 5, "Sunday": 6}
    df["day_of_week_encoded"] = df["day_of_week"].map(dow_map).fillna(0).astype(int)

    # 2. Calculate rolling features
    df = calculate_rolling_features(df)

    # Define targets for multi-horizon training
    # Horizons: 30m, 1h, 6h, 24h -> mapped to shifts of 1, 3, 18, 72 rows.
    horizons = {"30m": 1, "1h": 3, "6h": 18, "24h": 72}
    
    # We will generate a training dataset where 'horizon_minutes' is a feature.
    # To do this, we duplicate the training dataset for each horizon and append them!
    multi_horizon_dfs = []
    
    # Target columns
    target_bases = {
        "beds_required": "general_beds_occupied",
        "icu_beds_required": "icu_beds_occupied",
        "doctors_required": "doctors_occupied",
        "nurses_required": "nurses_occupied",
        "ventilators_required": "ventilators_occupied",
        "oxygen_required": "oxygen_utilization",
        "queue_required": "wait_time",
        "ambulances_required": "ambulance_requests",
        "load_required": "hospital_load_index",
        "pressure_required": "overload_risk_score",
        "availability_required": "general_beds_available"
    }
    
    for h_name, shift_rows in horizons.items():
        h_df = df.copy()
        
        # Set horizon feature in minutes
        horizon_val = 30 if h_name == "30m" else (60 if h_name == "1h" else (360 if h_name == "6h" else 1440))
        h_df["horizon_minutes"] = float(horizon_val)
        
        # Calculate shifted targets
        for target_key, base_col in target_bases.items():
            h_df[f"target_{target_key}"] = h_df[base_col].shift(-shift_rows)
            # Backfill/forwardfill targets
            h_df[f"target_{target_key}"] = h_df[f"target_{target_key}"].ffill().fillna(h_df[base_col])
            
        multi_horizon_dfs.append(h_df)
        
    combined_df = pd.concat(multi_horizon_dfs, ignore_index=True)

    os.makedirs(PROCESSED_DIR, exist_ok=True)
    combined_df.to_csv(PROCESSED_CLASSIFICATION_CSV, index=False)
    print(f"Saved multi-horizon processed dataset to {PROCESSED_CLASSIFICATION_CSV} (Shape: {combined_df.shape})")

    # 3. Create hourly aggregates for Prophet time series
    print("Creating hourly aggregates...")
    hourly_df = df.set_index("parsed_timestamp")
    
    hourly_admissions = hourly_df["admitted"].resample("H").sum().fillna(0)
    
    # Simulate discharges as lag of admissions (e.g. median LoS is 4 hours)
    hourly_discharges = hourly_admissions.shift(4).fillna(0)
    np.random.seed(42)
    hourly_discharges = (hourly_discharges * 0.9 + np.random.poisson(0.5, len(hourly_discharges))).round().astype(int)

    hourly_oxygen = hourly_df["oxygen_utilization"].resample("H").mean().ffill().bfill()
    hourly_ventilators = hourly_df["ventilators_occupied"].resample("H").mean().ffill().bfill()

    prophet_df = pd.DataFrame({
        "ds": hourly_admissions.index,
        "admissions": hourly_admissions.values,
        "discharges": hourly_discharges.values,
        "oxygen": hourly_oxygen.values,
        "ventilators": hourly_ventilators.values
    })

    prophet_df.to_csv(PROCESSED_FORECASTING_CSV, index=False)
    print(f"Saved forecasting dataset to {PROCESSED_FORECASTING_CSV} (Shape: {prophet_df.shape})")

if __name__ == "__main__":
    main()

import argparse
import os
import random
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

DEFAULT_OUTPUT = "datasets/MediFlow_AI_Synthetic_Dataset.csv"

DEPARTMENTS = ["Emergency", "ICU", "Cardiology", "Neurology", "Pediatrics", "Orthopedics", "General Medicine"]
ARRIVAL_MODES = ["Walk-in", "Ambulance", "Transfer"]
TRIAGE_LEVELS = ["Critical", "Urgent", "Semi-Urgent", "Non-Urgent"]
GENDERS = ["Male", "Female"]


def sigmoid(value: float) -> float:
    return 1 / (1 + np.exp(-value))


def build_synthetic_dataset(rows: int = 2500, seed: int = 42) -> pd.DataFrame:
    random.seed(seed)
    np.random.seed(seed)

    start = datetime(2026, 1, 1, 0, 0)
    records = []

    for idx in range(rows):
        timestamp = start + timedelta(minutes=int(idx * random.uniform(8, 24)))
        hour = timestamp.hour
        day_of_week = timestamp.strftime("%A")
        is_weekend = int(timestamp.weekday() >= 5)

        department = random.choices(
            DEPARTMENTS,
            weights=[0.28, 0.12, 0.14, 0.1, 0.13, 0.1, 0.13],
            k=1,
        )[0]
        arrival_mode = random.choices(ARRIVAL_MODES, weights=[0.62, 0.25, 0.13], k=1)[0]
        triage_level = random.choices(TRIAGE_LEVELS, weights=[0.12, 0.28, 0.36, 0.24], k=1)[0]

        age = int(np.clip(np.random.normal(44, 24), 1, 95))
        emergency_severity_level = {"Critical": 1, "Urgent": 2, "Semi-Urgent": 3, "Non-Urgent": 4}[triage_level]
        if department in ("ICU", "Cardiology") and emergency_severity_level > 2:
            emergency_severity_level -= 1

        peak_pressure = 1 if 9 <= hour <= 13 or 18 <= hour <= 23 else 0
        ambulance_requests = int(np.clip(np.random.poisson(2 + peak_pressure * 2 + (arrival_mode == "Ambulance") * 3), 0, 16))
        icu_beds_available = int(np.clip(np.random.normal(26 - ambulance_requests - peak_pressure * 5, 12), 0, 55))
        general_beds_available = int(np.clip(np.random.normal(155 - ambulance_requests * 4 - peak_pressure * 18, 45), 0, 260))
        doctor_availability = int(np.clip(np.random.normal(26 - peak_pressure * 5, 8), 3, 45))
        nurse_availability = int(np.clip(np.random.normal(58 - peak_pressure * 8, 16), 8, 95))
        oxygen_utilization = round(float(np.clip(np.random.normal(58 + ambulance_requests * 3 + peak_pressure * 8, 13), 25, 100)), 2)
        ventilator_availability = int(np.clip(np.random.normal(12 - ambulance_requests * 0.55, 5), 0, 24))
        wait_time = int(np.clip(np.random.normal(22 + peak_pressure * 20 + ambulance_requests * 2 - doctor_availability * 0.3, 15), 2, 130))

        pressure_score = (
            emergency_severity_level * -0.8
            + ambulance_requests * 0.18
            + wait_time * 0.018
            + oxygen_utilization * 0.012
            - icu_beds_available * 0.025
            - doctor_availability * 0.018
            + (department in ("ICU", "Emergency", "Cardiology")) * 0.45
            + (age >= 70) * 0.25
        )
        admission_probability = sigmoid(pressure_score)
        admitted = int(random.random() < admission_probability)

        capacity_risk_score = round(float(np.clip(100 - general_beds_available * 0.28 - icu_beds_available * 0.75 + oxygen_utilization * 0.45 + ambulance_requests * 2.5, 0, 100)), 2)
        hospital_load_index = round(float(np.clip(wait_time * 0.32 + ambulance_requests * 3.2 + oxygen_utilization * 0.25 + peak_pressure * 12, 0, 100)), 2)
        overload_risk_score = round(float(np.clip(capacity_risk_score * 0.48 + hospital_load_index * 0.38 + (doctor_availability < 10) * 15, 0, 100)), 2)

        if overload_risk_score >= 75:
            alert_level = "Critical"
            capacity_category = "High"
        elif overload_risk_score >= 55:
            alert_level = "Warning"
            capacity_category = "Medium"
        else:
            alert_level = "Normal"
            capacity_category = "Low"

        records.append({
            "patient_id": f"P{idx + 1:06d}",
            "timestamp": timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "age": age,
            "gender": random.choice(GENDERS),
            "department": department,
            "arrival_mode": arrival_mode,
            "triage_level": triage_level,
            "wait_time": wait_time,
            "emergency_severity_level": emergency_severity_level,
            "admitted": admitted,
            "icu_beds_available": icu_beds_available,
            "general_beds_available": general_beds_available,
            "doctor_availability": doctor_availability,
            "nurse_availability": nurse_availability,
            "ambulance_requests": ambulance_requests,
            "oxygen_utilization": oxygen_utilization,
            "ventilator_availability": ventilator_availability,
            "capacity_category": capacity_category,
            "capacity_risk_score": capacity_risk_score,
            "hospital_load_index": hospital_load_index,
            "overload_risk_score": overload_risk_score,
            "alert_level": alert_level,
            "hour": hour,
            "day_of_week": day_of_week,
            "is_weekend": is_weekend,
        })

    return pd.DataFrame(records)


def main():
    parser = argparse.ArgumentParser(description="Generate MediFlow synthetic hospital operations training data.")
    parser.add_argument("--rows", type=int, default=2500)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output", default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    df = build_synthetic_dataset(rows=args.rows, seed=args.seed)
    df.to_csv(args.output, index=False)
    print(f"Synthetic training dataset saved to {args.output} with shape {df.shape}")


if __name__ == "__main__":
    main()

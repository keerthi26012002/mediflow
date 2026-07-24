import pandas as pd
import numpy as np
import random
from datetime import datetime, timedelta

# ----------------------------
# Configuration
# ----------------------------

random.seed(42)
np.random.seed(42)

NUM_RECORDS = 10000

departments = [
    "Emergency",
    "ICU",
    "Cardiology",
    "Orthopedics",
    "Pediatrics",
    "Neurology"
]

arrival_modes = [
    "Walk-in",
    "Ambulance",
    "Referral",
    "Transfer"
]

triage_levels = [
    "Critical",
    "Urgent",
    "Semi-Urgent",
    "Non-Urgent"
]

# ----------------------------
# Generate Data
# ----------------------------

rows = []

start_date = datetime.now() - timedelta(days=180)

for i in range(NUM_RECORDS):

    # Random timestamp in last 6 months
    timestamp = start_date + timedelta(
        minutes=random.randint(0, 180 * 24 * 60)
    )

    hour = timestamp.hour

    day_of_week = timestamp.strftime("%A")

    is_weekend = (
        1 if timestamp.weekday() >= 5 else 0
    )

    # Patient Information
    age = random.randint(1, 95)

    gender = random.choice([
        "Male",
        "Female"
    ])

    department = random.choice(
        departments
    )

    arrival_mode = random.choices(
        arrival_modes,
        weights=[50, 20, 20, 10]
    )[0]

    triage_level = random.choices(
        triage_levels,
        weights=[10, 25, 35, 30]
    )[0]

    # Severity Mapping
    severity_map = {
        "Critical": 1,
        "Urgent": 2,
        "Semi-Urgent": 3,
        "Non-Urgent": 4
    }

    emergency_severity_level = severity_map[
        triage_level
    ]

    # Wait Time
    wait_time = max(
        1,
        int(np.random.normal(
            loc=30,
            scale=15
        ))
    )

    # Resource Metrics
    icu_beds_available = random.randint(
        0,
        50
    )

    general_beds_available = random.randint(
        20,
        300
    )

    doctor_availability = random.randint(
        5,
        40
    )

    nurse_availability = random.randint(
        10,
        80
    )

    ambulance_requests = random.randint(
        0,
        15
    )

    oxygen_utilization = round(
        random.uniform(40, 100),
        2
    )

    ventilator_availability = random.randint(
        0,
        25
    )

    # WHO Capacity Inspired Features
    capacity_risk_score = round(
        random.uniform(10, 95),
        2
    )

    if capacity_risk_score > 70:
        capacity_category = "Low"
    elif capacity_risk_score > 40:
        capacity_category = "Medium"
    else:
        capacity_category = "High"

    # Derived Metrics
    hospital_load_index = round(
        (
            (50 - icu_beds_available) * 0.4
            + ambulance_requests * 0.6
            + oxygen_utilization * 0.3
        ),
        2
    )

    overload_risk_score = round(
        min(
            100,
            (
                hospital_load_index * 0.8
                + capacity_risk_score * 0.2
            )
        ),
        2
    )

    # Alert Level
    if overload_risk_score > 85:
        alert_level = "Critical"

    elif overload_risk_score > 70:
        alert_level = "High"

    elif overload_risk_score > 50:
        alert_level = "Warning"

    else:
        alert_level = "Normal"

    # Admission Logic
    admitted = int(
        (
            emergency_severity_level <= 2
        )
        and
        (
            department in [
                "Emergency",
                "ICU",
                "Cardiology"
            ]
            or wait_time < 20
        )
    )

    rows.append({

        # Patient Info
        "patient_id":
            f"P{i+1:06d}",

        "timestamp":
            timestamp,

        "age":
            age,

        "gender":
            gender,

        "department":
            department,

        "arrival_mode":
            arrival_mode,

        "triage_level":
            triage_level,

        "wait_time":
            wait_time,

        "emergency_severity_level":
            emergency_severity_level,

        "admitted":
            admitted,

        # Resource Metrics
        "icu_beds_available":
            icu_beds_available,

        "general_beds_available":
            general_beds_available,

        "doctor_availability":
            doctor_availability,

        "nurse_availability":
            nurse_availability,

        "ambulance_requests":
            ambulance_requests,

        "oxygen_utilization":
            oxygen_utilization,

        "ventilator_availability":
            ventilator_availability,

        # Capacity Metrics
        "capacity_category":
            capacity_category,

        "capacity_risk_score":
            capacity_risk_score,

        # Operational Metrics
        "hospital_load_index":
            hospital_load_index,

        "overload_risk_score":
            overload_risk_score,

        "alert_level":
            alert_level,

        # Time Features
        "hour":
            hour,

        "day_of_week":
            day_of_week,

        "is_weekend":
            is_weekend
    })

# ----------------------------
# Create DataFrame
# ----------------------------

df = pd.DataFrame(rows)

# Save Dataset

df.to_csv(
    "MediFlow_AI_Synthetic_Dataset.csv",
    index=False
)

print(df.head())

print("\nDataset Shape:", df.shape)

print(
    "\nSaved as: MediFlow_AI_Synthetic_Dataset.csv"
)
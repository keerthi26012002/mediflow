import time
import json
import hashlib
import os
import pandas as pd
from faker import Faker
from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable

# Constants
CSV_PATH = "datasets/Hospital ER_Data.csv"
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")

TOPIC_ADMISSION = os.getenv("TOPIC_ADMISSION", "hospital.patient.admission")
TOPIC_DISCHARGE = os.getenv("TOPIC_DISCHARGE", "hospital.patient.discharge")
TOPIC_ICU = os.getenv("TOPIC_ICU", "hospital.resource.icu")
TOPIC_STAFF = os.getenv("TOPIC_STAFF", "hospital.staff.status")
TOPIC_AMBULANCE = os.getenv("TOPIC_AMBULANCE", "hospital.ambulance.request")
TOPIC_OXYGEN = os.getenv("TOPIC_OXYGEN", "hospital.resource.oxygen")

def get_deterministic_seed(timestamp_str: str) -> int:
    """Generate a deterministic seed integer from a timestamp string."""
    return int(hashlib.md5(timestamp_str.encode("utf-8")).hexdigest(), 16) % 100000000

def derive_severity_level(wait_time: int, department: str) -> int:
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
    if 6 <= hour < 14:
        return 0
    if 14 <= hour < 22:
        return 1
    return 2

def run_producer():
    print(f"Loading dataset from {CSV_PATH}...")
    try:
        df = pd.read_csv(CSV_PATH)
    except FileNotFoundError:
        print(f"Error: Dataset not found at {CSV_PATH}. Please ensure it exists.")
        return

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
    
    df["department"] = df["department"].fillna("Self-Referral")
    df["satisfaction_score"] = df["satisfaction_score"].fillna(3.0)

    # Sort by timestamp to stream chronologically
    df["parsed_time"] = pd.to_datetime(df["timestamp"], format="%d-%m-%Y %H:%M")
    df = df.sort_values(by="parsed_time").reset_index(drop=True)

    print("Initializing Kafka Producer...")
    producer = None
    retries = 3
    for i in range(retries):
        try:
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                acks="all",
                retries=5
            )
            print("Successfully connected to Kafka.")
            break
        except NoBrokersAvailable:
            print(f"Kafka broker not available at {KAFKA_BOOTSTRAP}. Retrying in 5 seconds... ({i+1}/{retries})")
            if i < retries - 1:
                time.sleep(5)
            else:
                print("\n[WARNING] Could not connect to Kafka. Running in MOCK/PRINT mode.")
                print("To connect to a real Kafka instance, please run: docker compose up -d\n")

    fake = Faker()
    last_icu_time = 0
    last_staff_time = 0
    last_ambulance_time = 0
    last_oxygen_time = 0
    
    discharges = [] # List of (discharge_time, discharge_event)
    
    print("Starting streaming simulation. Press Ctrl+C to stop.")
    for idx, row in df.iterrows():
        ts_str = row["timestamp"]
        event_time = row["parsed_time"]
        seed = get_deterministic_seed(ts_str)
        fake.seed_instance(seed)
        
        # Generate seeded simulated fields
        icu_beds_available = fake.random_int(min=0, max=50)
        ambulance_requests = fake.random_int(min=0, max=10)
        doctor_availability = fake.random_int(min=5, max=30)
        nurse_availability = fake.random_int(min=12, max=70)
        oxygen_utilization = round(fake.random.uniform(40.0, 100.0), 2)
        ventilator_availability = fake.random_int(min=0, max=18)
        severity_level = derive_severity_level(row["wait_time"], row["department"])
        
        # 1. Patient Admission Event
        event = {
            "patient_id": row["patient_id"],
            "timestamp": ts_str,
            "age": int(row["age"]),
            "gender": row["gender"],
            "wait_time": int(row["wait_time"]),
            "department": row["department"],
            "admitted": bool(row["admitted"]),
            "satisfaction_score": float(row["satisfaction_score"]),
            "race": row["race"],
            "icu_beds_available": icu_beds_available,
            "ambulance_requests": ambulance_requests,
            "doctor_availability": doctor_availability,
            "oxygen_utilization": oxygen_utilization,
            "emergency_severity_level": severity_level
        }
        
        # Stream patient admission event
        if producer:
            try:
                producer.send(TOPIC_ADMISSION, value=event)
                producer.flush()
                print(f"Sent Admission: {row['patient_id']} | Admitted: {row['admitted']}")
            except Exception as e:
                print(f"Error sending admission to Kafka: {e}")
        else:
            print(f"[MOCK] Sent Admission: {event}")

        # If admitted, schedule a discharge event
        if bool(row["admitted"]):
            discharge_delay = fake.random_int(min=5, max=15)
            discharge_time = time.time() + discharge_delay
            discharge_event = {
                "patient_id": row["patient_id"],
                "timestamp": (event_time + timedelta(minutes=discharge_delay*10)).strftime("%d-%m-%Y %H:%M"),
                "department": row["department"],
                "discharge_reason": fake.random_element(elements=("Recovered", "Transferred", "Self-Discharge", "Referred"))
            }
            discharges.append((discharge_time, discharge_event))

        # Check and send scheduled discharges
        current_time = time.time()
        for d_time, d_event in list(discharges):
            if current_time >= d_time:
                if producer:
                    try:
                        producer.send(TOPIC_DISCHARGE, value=d_event)
                        producer.flush()
                        print(f"Sent Discharge: {d_event['patient_id']}")
                    except Exception as e:
                        print(f"Error sending discharge to Kafka: {e}")
                else:
                    print(f"[MOCK] Sent Discharge: {d_event}")
                discharges.remove((d_time, d_event))

        # Periodically send other telemetry streams
        # Staff status (Every 15s)
        if (current_time - last_staff_time) >= 15:
            staff_event = {
                "timestamp": ts_str,
                "shift": get_shift(event_time.hour),
                "doctor_availability": doctor_availability,
                "nurse_availability": nurse_availability
            }
            if producer:
                try:
                    producer.send(TOPIC_STAFF, value=staff_event)
                    producer.flush()
                    print(f"Sent Staff Status: Doctors available={doctor_availability}")
                except Exception as e:
                    print(f"Error sending staff status to Kafka: {e}")
            else:
                print(f"[MOCK] Sent Staff Status: {staff_event}")
            last_staff_time = current_time

        # Ambulance requests (Every 20s)
        if (current_time - last_ambulance_time) >= 20:
            amb_event = {
                "timestamp": ts_str,
                "ambulance_requests": ambulance_requests
            }
            if producer:
                try:
                    producer.send(TOPIC_AMBULANCE, value=amb_event)
                    producer.flush()
                    print(f"Sent Ambulance Update: Requests={ambulance_requests}")
                except Exception as e:
                    print(f"Error sending ambulance status to Kafka: {e}")
            else:
                print(f"[MOCK] Sent Ambulance Update: {amb_event}")
            last_ambulance_time = current_time

        # Oxygen utilization (Every 25s)
        if (current_time - last_oxygen_time) >= 25:
            oxy_event = {
                "timestamp": ts_str,
                "oxygen_utilization": oxygen_utilization
            }
            if producer:
                try:
                    producer.send(TOPIC_OXYGEN, value=oxy_event)
                    producer.flush()
                    print(f"Sent Oxygen Update: {oxygen_utilization}%")
                except Exception as e:
                    print(f"Error sending oxygen status to Kafka: {e}")
            else:
                print(f"[MOCK] Sent Oxygen Update: {oxy_event}")
            last_oxygen_time = current_time

        # ICU status snapshots (Every 30s)
        if (current_time - last_icu_time) >= 30:
            icu_event = {
                "timestamp": ts_str,
                "icu_beds_available": icu_beds_available,
                "oxygen_utilization": oxygen_utilization,
                "doctor_availability": doctor_availability,
                "ambulance_requests": ambulance_requests,
                "ventilator_availability": ventilator_availability
            }
            if producer:
                try:
                    producer.send(TOPIC_ICU, value=icu_event)
                    producer.flush()
                    print(f"Sent ICU Snapshot: Beds available={icu_beds_available}")
                except Exception as e:
                    print(f"Error sending ICU snapshot to Kafka: {e}")
            else:
                print(f"[MOCK] Sent ICU Snapshot: {icu_event}")
            last_icu_time = current_time

        time.sleep(1)

if __name__ == "__main__":
    try:
        run_producer()
    except KeyboardInterrupt:
        print("\nStreaming stopped by user.")

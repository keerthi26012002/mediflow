import time
import json
import hashlib
import pandas as pd
from faker import Faker
from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable

# Constants
CSV_PATH = "datasets/Hospital ER_Data.csv"
KAFKA_BOOTSTRAP = "localhost:9092"
TOPIC_PATIENT_FLOW = "patient-flow"
TOPIC_ICU_STATUS = "icu-status"

def get_deterministic_seed(timestamp_str: str) -> int:
    """Generate a deterministic seed integer from a timestamp string."""
    return int(hashlib.md5(timestamp_str.encode("utf-8")).hexdigest(), 16) % 100000000

def derive_severity_level(wait_time: int, department: str) -> int:
    """Derive severity level (1-5, where 1 is highest severity) based on wait time and department."""
    # Let's say if wait time is short, it could be high severity (needs immediate attention) 
    # or department is ICU/Cardiology. Let's create a deterministic mapping.
    dept = str(department).lower()
    if "card" in dept or "icu" in dept or "emerg" in dept:
        base = 1
    elif "ortho" in dept or "ped" in dept:
        base = 3
    else:
        base = 4
        
    # Adjust based on wait time
    if wait_time < 15:
        severity = base
    elif wait_time < 30:
        severity = min(5, base + 1)
    elif wait_time < 60:
        severity = min(5, base + 2)
    else:
        severity = min(5, base + 3)
        
    return max(1, min(5, severity))

def run_producer():
    print(f"Loading dataset from {CSV_PATH}...")
    try:
        df = pd.read_csv(CSV_PATH)
    except FileNotFoundError:
        print(f"Error: Dataset not found at {CSV_PATH}. Please ensure it exists.")
        return

    # Map columns to logical fields and handle missing department values
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
    
    # Fill NaNs
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
    
    print("Starting streaming simulation. Press Ctrl+C to stop.")
    for idx, row in df.iterrows():
        ts_str = row["timestamp"]
        seed = get_deterministic_seed(ts_str)
        fake.seed_instance(seed)
        
        # Generate seeded simulated fields
        icu_beds_available = fake.random_int(min=0, max=50)
        ambulance_requests = fake.random_int(min=0, max=10)
        doctor_availability = fake.random_int(min=5, max=30)
        oxygen_utilization = round(fake.random.uniform(40.0, 100.0), 2)
        severity_level = derive_severity_level(row["wait_time"], row["department"])
        
        # Construct patient flow event
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
        
        # Stream patient event
        if producer:
            try:
                producer.send(TOPIC_PATIENT_FLOW, value=event)
                producer.flush()
                print(f"Sent Patient Flow Event: {row['patient_id']} | Admitted: {row['admitted']}")
            except Exception as e:
                print(f"Error sending event to Kafka: {e}")
        else:
            print(f"[MOCK] Sent Patient Flow Event: {event}")

        # Send ICU snapshot every 30 records (equivalent to 30 seconds if sleep is 1s)
        current_time = time.time()
        if (current_time - last_icu_time) >= 30:
            icu_event = {
                "timestamp": ts_str,
                "icu_beds_available": icu_beds_available,
                "oxygen_utilization": oxygen_utilization,
                "doctor_availability": doctor_availability,
                "ambulance_requests": ambulance_requests
            }
            if producer:
                try:
                    producer.send(TOPIC_ICU_STATUS, value=icu_event)
                    producer.flush()
                    print(f"Sent ICU Snapshot to Kafka: {icu_event}")
                except Exception as e:
                    print(f"Error sending ICU status to Kafka: {e}")
            else:
                print(f"[MOCK] Sent ICU Snapshot: {icu_event}")
            last_icu_time = current_time

        time.sleep(1)

if __name__ == "__main__":
    try:
        run_producer()
    except KeyboardInterrupt:
        print("\nStreaming stopped by user.")

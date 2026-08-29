import time
import json
import os
import random
from datetime import datetime
import pandas as pd
from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable

# Dataset candidate paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CANDIDATE_DATASETS = [
    os.path.join(BASE_DIR, "datasets", "MediFlow_AI_Synthetic_Dataset (1).csv"),
    os.path.join(BASE_DIR, "datasets", "MediFlow_AI_Synthetic_Dataset.csv"),
    os.path.join(BASE_DIR, "datasets", "Hospital ER_Data.csv"),
    "datasets/MediFlow_AI_Synthetic_Dataset (1).csv",
    "datasets/MediFlow_AI_Synthetic_Dataset.csv"
]
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
TICK_INTERVAL = float(os.getenv("STREAM_TICK_INTERVAL_SEC", "1.5"))

# v2.0 Topics
TOPIC_PATIENT_ADMISSION = "hospital.patient.admission"
TOPIC_PATIENT_DISCHARGE = "hospital.patient.discharge"
TOPIC_PATIENT_TRANSFER = "hospital.patient.transfer"
TOPIC_PATIENT_EMERGENCY = "hospital.patient.emergency"
TOPIC_RESOURCE_BEDS = "hospital.resource.beds"
TOPIC_RESOURCE_ICU = "hospital.resource.icu"
TOPIC_RESOURCE_STAFF = "hospital.resource.staff"
TOPIC_RESOURCE_OXYGEN = "hospital.resource.oxygen"
TOPIC_RESOURCE_VENTILATOR = "hospital.resource.ventilator"
TOPIC_ALERTS = "hospital.alerts"
TOPIC_PREDICTIONS = "hospital.predictions"
TOPIC_AUDIT_LOGS = "hospital.audit.logs"

def resolve_dataset():
    for p in CANDIDATE_DATASETS:
        if os.path.exists(p):
            return p
    return None

def send_event(producer, topic, payload):
    """Sends an event asynchronously to Kafka without blocking flush."""
    if producer:
        try:
            producer.send(topic, value=payload)
        except Exception as e:
            print(f"[Producer] Error queuing to {topic}: {e}")
    else:
        print(f"[MOCK-PRODUCER] Topic: {topic} | Seq: {payload.get('sequence_id')} | Patient: {payload.get('patient_id', 'RESOURCE')}")

def run_producer():
    csv_path = resolve_dataset()
    if not csv_path:
        print("Error: No synthetic dataset CSV found.")
        return

    print(f"Loading synthetic dataset from {csv_path}...")
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return

    # Sort chronologically if timestamp exists
    if "timestamp" in df.columns:
        df["parsed_time"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values(by="parsed_time").reset_index(drop=True)

    print(f"Initializing Kafka Producer connected to {KAFKA_BOOTSTRAP}...")
    producer = None
    retries = 3
    for i in range(retries):
        try:
            producer = KafkaProducer(
                bootstrap_servers=KAFKA_BOOTSTRAP,
                value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                acks="all",
                retries=3
            )
            print("Successfully connected to Kafka.")
            break
        except NoBrokersAvailable:
            print(f"Kafka broker not available at {KAFKA_BOOTSTRAP}. Retrying... ({i+1}/{retries})")
            if i < retries - 1:
                time.sleep(2)
            else:
                print("\n[WARNING] Could not connect to Kafka. Running in MOCK/PRINT mode.\n")

    # Track active admitted patients to simulate natural discharges
    active_admissions = []
    tick_id = 0
    sequence_id = 0

    print("Starting continuous real-time streaming simulation. Press Ctrl+C to stop.")
    while True:
        for idx, row in df.iterrows():
            tick_id += 1
            sequence_id += 1

            # Use current wall-clock simulation time
            sim_time = datetime.now()
            ts_str = sim_time.strftime("%Y-%m-%d %H:%M:%S")
            patient_id = str(row["patient_id"])

            tick_meta = {
                "tick_id": tick_id,
                "sequence_id": sequence_id,
                "timestamp": ts_str
            }

            # 1. Emergency Arrival Event
            emergency_event = {
                **tick_meta,
                "patient_id": patient_id,
                "age": int(row["age"]),
                "gender": str(row["gender"]),
                "arrival_mode": str(row["arrival_mode"]),
                "triage_level": str(row["triage_level"]),
                "wait_time": int(row["wait_time"]),
                "emergency_severity_level": int(row["emergency_severity_level"]),
                "department": str(row["department"]),
                "admitted": bool(row["admitted"]),
                "icu_beds_available": int(row["icu_beds_available"]),
                "general_beds_available": int(row["general_beds_available"]),
                "doctor_availability": int(row["doctor_availability"]),
                "nurse_availability": int(row["nurse_availability"]),
                "ambulance_requests": int(row["ambulance_requests"]),
                "oxygen_utilization": float(row["oxygen_utilization"]),
                "ventilator_availability": int(row["ventilator_availability"])
            }
            send_event(producer, TOPIC_PATIENT_EMERGENCY, emergency_event)

            # 2. Admission Event (if admitted flag is true)
            if row["admitted"] == 1:
                admission_event = {
                    **tick_meta,
                    "patient_id": patient_id,
                    "age": int(row["age"]),
                    "department": str(row["department"]),
                    "triage_level": str(row["triage_level"])
                }
                send_event(producer, TOPIC_PATIENT_ADMISSION, admission_event)
                
                # Store in active admissions with a simulated discharge tick
                active_admissions.append({
                    "patient_id": patient_id,
                    "discharge_tick": tick_id + random.randint(5, 15),
                    "department": str(row["department"])
                })

            # 3. Transfer Event (simulated transfer to ICU if department is ICU)
            if str(row["department"]) == "ICU":
                transfer_event = {
                    **tick_meta,
                    "patient_id": patient_id,
                    "from_department": "Emergency",
                    "to_department": "ICU"
                }
                send_event(producer, TOPIC_PATIENT_TRANSFER, transfer_event)
                send_event(producer, TOPIC_RESOURCE_ICU, {
                    **tick_meta,
                    "icu_beds_available": int(row["icu_beds_available"]),
                    "oxygen_utilization": float(row["oxygen_utilization"])
                })

            # 4. Bed Allocation Snapshot
            bed_event = {
                **tick_meta,
                "general_beds_available": int(row["general_beds_available"]),
                "icu_beds_available": int(row["icu_beds_available"])
            }
            send_event(producer, TOPIC_RESOURCE_BEDS, bed_event)

            # 5. Staff Status Snapshot
            staff_event = {
                **tick_meta,
                "doctor_availability": int(row["doctor_availability"]),
                "nurse_availability": int(row["nurse_availability"])
            }
            send_event(producer, TOPIC_RESOURCE_STAFF, staff_event)

            # 6. Oxygen Inflow Snapshot
            oxygen_event = {
                **tick_meta,
                "oxygen_utilization": float(row["oxygen_utilization"])
            }
            send_event(producer, TOPIC_RESOURCE_OXYGEN, oxygen_event)

            # 7. Ventilator Status Snapshot
            ventilator_event = {
                **tick_meta,
                "ventilator_availability": int(row["ventilator_availability"])
            }
            send_event(producer, TOPIC_RESOURCE_VENTILATOR, ventilator_event)

            # 8. Check and Emit Discharges
            discharged_patients = []
            for adm in active_admissions:
                if tick_id >= adm["discharge_tick"]:
                    discharge_event = {
                        **tick_meta,
                        "patient_id": adm["patient_id"],
                        "department": adm["department"]
                    }
                    send_event(producer, TOPIC_PATIENT_DISCHARGE, discharge_event)
                    discharged_patients.append(adm)
            
            for item in discharged_patients:
                active_admissions.remove(item)

            # 9. Audit Log
            audit_event = {
                **tick_meta,
                "action": "PROCESSED_TICK",
                "details": f"Processed tick #{tick_id} for patient {patient_id}"
            }
            send_event(producer, TOPIC_AUDIT_LOGS, audit_event)

            # Single atomic flush per tick for optimal network performance
            if producer:
                try:
                    producer.flush()
                except Exception as e:
                    print(f"Error flushing tick #{tick_id}: {e}")

            if tick_id % 10 == 0:
                print(f"[Producer Tick #{tick_id}] Emitted stream tick at {ts_str} (Active admissions: {len(active_admissions)})")

            time.sleep(TICK_INTERVAL)

if __name__ == "__main__":
    try:
        run_producer()
    except KeyboardInterrupt:
        print("\nStreaming simulation stopped.")

import time
import json
import os
import random
import pandas as pd
from kafka import KafkaProducer
from kafka.errors import NoBrokersAvailable

# Constants
CSV_PATH = "datasets/MediFlow_AI_Synthetic_Dataset (1).csv"
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")

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

def run_producer():
    print(f"Loading synthetic dataset from {CSV_PATH}...")
    if not os.path.exists(CSV_PATH):
        print(f"Error: Dataset not found at {CSV_PATH}.")
        return

    try:
        df = pd.read_csv(CSV_PATH)
    except Exception as e:
        print(f"Error reading CSV: {e}")
        return

    # Sort by timestamp to stream chronologically
    df["parsed_time"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values(by="parsed_time").reset_index(drop=True)

    print("Initializing Kafka Producer...")
    producer = None
    retries = 2
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

    # Track active admitted patients to simulate discharges
    active_admissions = []

    print("Starting streaming simulation. Press Ctrl+C to stop.")
    for idx, row in df.iterrows():
        ts_str = str(row["timestamp"])
        patient_id = str(row["patient_id"])
        
        # 1. Emergency Arrival Event
        emergency_event = {
            "patient_id": patient_id,
            "timestamp": ts_str,
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

        # Send Emergency Arrival
        send_event(producer, TOPIC_PATIENT_EMERGENCY, emergency_event)

        # 2. Admission Event (if admitted flag is true)
        if row["admitted"] == 1:
            admission_event = {
                "patient_id": patient_id,
                "timestamp": ts_str,
                "age": int(row["age"]),
                "department": str(row["department"]),
                "triage_level": str(row["triage_level"])
            }
            send_event(producer, TOPIC_PATIENT_ADMISSION, admission_event)
            
            # Store in active admissions with a simulated discharge time step
            active_admissions.append({
                "patient_id": patient_id,
                "discharge_tick": idx + random.randint(5, 15), # discharge after 5-15 ticks
                "department": str(row["department"])
            })

        # 3. Transfer Event (simulated transfer to ICU if department is ICU)
        if str(row["department"]) == "ICU":
            transfer_event = {
                "patient_id": patient_id,
                "timestamp": ts_str,
                "from_department": "Emergency",
                "to_department": "ICU"
            }
            send_event(producer, TOPIC_PATIENT_TRANSFER, transfer_event)
            send_event(producer, TOPIC_RESOURCE_ICU, {
                "timestamp": ts_str,
                "icu_beds_available": int(row["icu_beds_available"]),
                "oxygen_utilization": float(row["oxygen_utilization"])
            })

        # 4. Bed Allocation Snapshot
        bed_event = {
            "timestamp": ts_str,
            "general_beds_available": int(row["general_beds_available"]),
            "icu_beds_available": int(row["icu_beds_available"])
        }
        send_event(producer, TOPIC_RESOURCE_BEDS, bed_event)

        # 5. Staff Status Snapshot
        staff_event = {
            "timestamp": ts_str,
            "doctor_availability": int(row["doctor_availability"]),
            "nurse_availability": int(row["nurse_availability"])
        }
        send_event(producer, TOPIC_RESOURCE_STAFF, staff_event)

        # 6. Oxygen Inflow Snapshot
        oxygen_event = {
            "timestamp": ts_str,
            "oxygen_utilization": float(row["oxygen_utilization"])
        }
        send_event(producer, TOPIC_RESOURCE_OXYGEN, oxygen_event)

        # 7. Ventilator Status Snapshot
        ventilator_event = {
            "timestamp": ts_str,
            "ventilator_availability": int(row["ventilator_availability"])
        }
        send_event(producer, TOPIC_RESOURCE_VENTILATOR, ventilator_event)

        # 8. Check and Emit Discharges
        discharged_patients = []
        for adm in active_admissions:
            if idx >= adm["discharge_tick"]:
                discharge_event = {
                    "patient_id": adm["patient_id"],
                    "timestamp": ts_str,
                    "department": adm["department"]
                }
                send_event(producer, TOPIC_PATIENT_DISCHARGE, discharge_event)
                discharged_patients.append(adm)
        
        for item in discharged_patients:
            active_admissions.remove(item)

        # 9. Audit Logs
        audit_event = {
            "timestamp": ts_str,
            "action": "PROCESSED_TICK",
            "details": f"Processed event tick {idx} for patient {patient_id}"
        }
        send_event(producer, TOPIC_AUDIT_LOGS, audit_event)

        time.sleep(1)

def send_event(producer, topic, payload):
    if producer:
        try:
            producer.send(topic, value=payload)
            producer.flush()
        except Exception as e:
            print(f"Error sending to {topic}: {e}")
    else:
        print(f"[MOCK-PRODUCER] Topic: {topic} | Data: {payload}")

if __name__ == "__main__":
    try:
        run_producer()
    except KeyboardInterrupt:
        print("\nStreaming simulation stopped.")

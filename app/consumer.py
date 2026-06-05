import os
import json
import asyncio
import threading
import time
from datetime import datetime, timedelta
from kafka import KafkaConsumer
from kafka.errors import NoBrokersAvailable
from app.db import (
    get_database,
    COLLECTION_PATIENT_EVENTS,
    COLLECTION_PREDICTIONS,
    COLLECTION_ICU_SNAPSHOTS,
    COLLECTION_ALERTS
)
from app.ml.inference import predict_admission
from app.websocket_manager import manager

# Environment Variables
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")
TOPIC_PATIENT_FLOW = os.getenv("TOPIC_PATIENT_FLOW", "patient-flow")
TOPIC_ICU_STATUS = os.getenv("TOPIC_ICU_STATUS", "icu-status")
OVERLOAD_THRESHOLD = int(os.getenv("OVERLOAD_THRESHOLD", "15"))

async def handle_patient_flow(event: dict):
    """Processes patient flow event, runs inference, saves to DB, and checks overload alerts."""
    try:
        db = get_database()
        
        # Parse timestamp
        try:
            event_time = datetime.strptime(event["timestamp"], "%d-%m-%Y %H:%M")
        except (ValueError, KeyError):
            event_time = datetime.now()
            event["timestamp"] = event_time.strftime("%d-%m-%Y %H:%M")
            
        event["parsed_timestamp"] = event_time
        
        # 1. Insert patient event
        # Strip MongoDB _id if present from previous operations
        event.pop("_id", None)
        await db[COLLECTION_PATIENT_EVENTS].insert_one(event.copy())
        
        # 2. Get prediction (stub in Phase 4, real in Phase 2)
        prediction = predict_admission(event)
        prediction["parsed_timestamp"] = event_time
        prediction.pop("_id", None)
        await db[COLLECTION_PREDICTIONS].insert_one(prediction.copy())
        
        # 3. Calculate rolling count of admitted patients in last hour
        one_hour_ago = event_time - timedelta(hours=1)
        admissions_count = await db[COLLECTION_PATIENT_EVENTS].count_documents({
            "admitted": True,
            "parsed_timestamp": {
                "$gte": one_hour_ago,
                "$lte": event_time
            }
        })
        
        print(f"Processed event for {event.get('patient_id')}. Admissions in last hour: {admissions_count}/{OVERLOAD_THRESHOLD}")
        
        # 4. Trigger Alert if overload threshold is breached
        if admissions_count > OVERLOAD_THRESHOLD:
            alert = {
                "timestamp": event["timestamp"],
                "message": f"Overload alert: {admissions_count} patient admissions in the last hour (threshold: {OVERLOAD_THRESHOLD})",
                "admissions_count": admissions_count,
                "threshold": OVERLOAD_THRESHOLD,
                "severity": "CRITICAL" if admissions_count > OVERLOAD_THRESHOLD * 1.5 else "WARNING",
                "parsed_timestamp": event_time
            }
            await db[COLLECTION_ALERTS].insert_one(alert.copy())
            
            # Prepare for JSON socket serialization
            alert.pop("parsed_timestamp", None)
            alert.pop("_id", None)
            await manager.broadcast(alert)
            print(f"Broadcasted live alert: {alert['message']}")

    except Exception as e:
        print(f"Error handling patient event: {e}")

async def handle_icu_snapshot(snapshot: dict):
    """Processes and logs ICU snapshots."""
    try:
        db = get_database()
        
        try:
            event_time = datetime.strptime(snapshot["timestamp"], "%d-%m-%Y %H:%M")
        except (ValueError, KeyError):
            event_time = datetime.now()
            snapshot["timestamp"] = event_time.strftime("%d-%m-%Y %H:%M")
            
        snapshot["parsed_timestamp"] = event_time
        snapshot.pop("_id", None)
        await db[COLLECTION_ICU_SNAPSHOTS].insert_one(snapshot)
        print(f"Processed ICU snapshot: Beds available={snapshot.get('icu_beds_available')}")
    except Exception as e:
        print(f"Error handling ICU snapshot: {e}")

def run_mock_ingestion_sync(loop: asyncio.AbstractEventLoop):
    """Fallback generator running inside consumer thread when Kafka is not available.
    It reads the CSV directly, applies feature engineering logic and generates events,
    inserting them directly into MongoDB to simulate the streaming pipeline."""
    import hashlib
    import pandas as pd
    from faker import Faker
    
    CSV_PATH = "datasets/Hospital ER_Data.csv"
    if not os.path.exists(CSV_PATH):
        print(f"[Mock Consumer] Error: Dataset CSV not found at {CSV_PATH}. Mock streaming aborted.")
        return
        
    print("[Mock Consumer] Loading CSV for mock streaming...")
    try:
        df = pd.read_csv(CSV_PATH)
    except Exception as e:
        print(f"[Mock Consumer] Error reading CSV: {e}")
        return
        
    # Standardize schema
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
    
    # Sort chronologically
    df["parsed_time"] = pd.to_datetime(df["timestamp"], format="%d-%m-%Y %H:%M")
    df = df.sort_values(by="parsed_time").reset_index(drop=True)
    
    fake = Faker()
    
    def get_deterministic_seed(timestamp_str: str) -> int:
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

    print("[Mock Consumer] Starting mock streaming loop. Press Ctrl+C in server to stop.")
    last_icu_time = 0
    
    # Loop infinitely to keep the simulation alive
    while True:
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
            
            # Dispatch to async handler
            asyncio.run_coroutine_threadsafe(handle_patient_flow(event), loop)
            
            # Dispatch ICU status every 30 iterations
            current_time = time.time()
            if (current_time - last_icu_time) >= 30:
                icu_event = {
                    "timestamp": ts_str,
                    "icu_beds_available": icu_beds_available,
                    "oxygen_utilization": oxygen_utilization,
                    "doctor_availability": doctor_availability,
                    "ambulance_requests": ambulance_requests
                }
                asyncio.run_coroutine_threadsafe(handle_icu_snapshot(icu_event), loop)
                last_icu_time = current_time
                
            time.sleep(1)

def run_consumer_thread(loop: asyncio.AbstractEventLoop):
    """Sync loop function running inside a background thread."""
    while True:
        print(f"Connecting background consumer to Kafka on {KAFKA_BOOTSTRAP}...")
        try:
            consumer = KafkaConsumer(
                TOPIC_PATIENT_FLOW,
                TOPIC_ICU_STATUS,
                bootstrap_servers=KAFKA_BOOTSTRAP,
                auto_offset_reset="latest",
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                group_id="mediflow-backend-group",
                consumer_timeout_ms=5000  # Non-blocking timeout so loop stays alive
            )
            print("Connected background consumer to Kafka.")
            
            while True:
                try:
                    # Fetch batch of messages
                    message_batch = consumer.poll(timeout_ms=1000)
                    for partition, messages in message_batch.items():
                        for msg in messages:
                            if msg.topic == TOPIC_PATIENT_FLOW:
                                asyncio.run_coroutine_threadsafe(handle_patient_flow(msg.value), loop)
                            elif msg.topic == TOPIC_ICU_STATUS:
                                asyncio.run_coroutine_threadsafe(handle_icu_snapshot(msg.value), loop)
                except Exception as e:
                    print(f"Error in Kafka consumer poll iteration: {e}")
                    break  # Break out to trigger reconnect
                
        except NoBrokersAvailable:
            print("Kafka brokers not available. Running in MOCK INGESTION mode (generating synthetic entries directly)...")
            run_mock_ingestion_sync(loop)
            break
        except Exception as e:
            print(f"Error starting Kafka consumer thread: {e}. Retrying in 10 seconds...")
            time.sleep(10)

def start_background_consumer():
    """Launches the background thread running the Kafka consumer loop."""
    loop = asyncio.get_running_loop()
    t = threading.Thread(target=run_consumer_thread, args=(loop,), daemon=True)
    t.start()
    print("Background consumer thread spawned.")

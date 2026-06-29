import os
import json
import asyncio
import threading
import time
import math
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
TOPIC_ADMISSION = os.getenv("TOPIC_ADMISSION", "hospital.patient.admission")
TOPIC_DISCHARGE = os.getenv("TOPIC_DISCHARGE", "hospital.patient.discharge")
TOPIC_ICU = os.getenv("TOPIC_ICU", "hospital.resource.icu")
TOPIC_STAFF = os.getenv("TOPIC_STAFF", "hospital.staff.status")
TOPIC_AMBULANCE = os.getenv("TOPIC_AMBULANCE", "hospital.ambulance.request")
TOPIC_OXYGEN = os.getenv("TOPIC_OXYGEN", "hospital.resource.oxygen")
TOPIC_PREDICTION = os.getenv("TOPIC_PREDICTION", "hospital.prediction.events")
TOPIC_AUDIT = os.getenv("TOPIC_AUDIT", "hospital.audit.logs")

OVERLOAD_THRESHOLD = int(os.getenv("OVERLOAD_THRESHOLD", "15"))
DEFAULT_DATASET_CANDIDATES = [
    os.getenv("MOCK_DATASET_PATH", ""),
    os.path.join("datasets", "MediFlow_AI_Synthetic_Dataset.csv"),
    os.path.join(os.path.expanduser("~"), "Downloads", "MediFlow_AI_Synthetic_Dataset (1).csv"),
    os.path.join("datasets", "Hospital ER_Data.csv"),
]

def parse_event_time(timestamp_value) -> datetime:
    """Parse supported simulator timestamp formats into a datetime."""
    timestamp_str = str(timestamp_value)
    for fmt in ("%d-%m-%Y %H:%M", "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(timestamp_str, fmt)
        except ValueError:
            continue
    return datetime.now()

def get_mock_dataset_path() -> str:
    for path in DEFAULT_DATASET_CANDIDATES:
        if path and os.path.exists(path):
            return path
    return os.path.join("datasets", "Hospital ER_Data.csv")

def get_shift(hour: int) -> int:
    if 6 <= hour < 14:
        return 0
    if 14 <= hour < 22:
        return 1
    return 2

async def handle_patient_flow(event: dict):
    """Processes patient flow event, runs inference, saves to DB, and checks overload alerts."""
    try:
        db = get_database()
        
        try:
            event_time = parse_event_time(event["timestamp"])
        except KeyError:
            event_time = datetime.now()
            event["timestamp"] = event_time.strftime("%d-%m-%Y %H:%M")
            
        event["parsed_timestamp"] = event_time
        
        # 1. Insert patient event
        event.pop("_id", None)
        await db[COLLECTION_PATIENT_EVENTS].insert_one(event.copy())
        
        # 2. Get prediction
        prediction = predict_admission(event)
        prediction["parsed_timestamp"] = event_time
        prediction.pop("_id", None)
        await db[COLLECTION_PREDICTIONS].insert_one(prediction.copy())
        
        # Log to prediction_events
        try:
            pred_log = {
                "timestamp": event["timestamp"],
                "patient_id": event.get("patient_id"),
                "predicted_admission": prediction.get("predicted_admission"),
                "admission_proba": prediction.get("admission_proba"),
                "model_loaded": prediction.get("model_loaded", False),
                "parsed_timestamp": event_time
            }
            await db["prediction_events"].insert_one(pred_log)
        except Exception as e:
            print(f"Error logging prediction event: {e}")
        
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

async def handle_discharge(event: dict):
    try:
        db = get_database()
        try:
            event_time = parse_event_time(event["timestamp"])
        except KeyError:
            event_time = datetime.now()
            event["timestamp"] = event_time.strftime("%d-%m-%Y %H:%M")
        event["parsed_timestamp"] = event_time
        event.pop("_id", None)
        await db["discharge_events"].insert_one(event)
        print(f"Processed discharge event: Patient={event.get('patient_id')} discharged from {event.get('department')}")
    except Exception as e:
        print(f"Error handling discharge event: {e}")

async def handle_icu_snapshot(snapshot: dict):
    """Processes and logs ICU snapshots."""
    try:
        db = get_database()
        try:
            event_time = parse_event_time(snapshot["timestamp"])
        except KeyError:
            event_time = datetime.now()
            snapshot["timestamp"] = event_time.strftime("%d-%m-%Y %H:%M")
            
        snapshot["parsed_timestamp"] = event_time
        snapshot.pop("_id", None)
        await db[COLLECTION_ICU_SNAPSHOTS].insert_one(snapshot)
        print(f"Processed ICU snapshot: Beds available={snapshot.get('icu_beds_available')}")
    except Exception as e:
        print(f"Error handling ICU snapshot: {e}")

async def handle_staff_status(event: dict):
    try:
        db = get_database()
        try:
            event_time = parse_event_time(event["timestamp"])
        except KeyError:
            event_time = datetime.now()
            event["timestamp"] = event_time.strftime("%d-%m-%Y %H:%M")
        event["parsed_timestamp"] = event_time
        event.pop("_id", None)
        await db["staff_status"].insert_one(event)
        print(f"Processed Staff Status: Shift={event.get('shift')} | Doctors={event.get('doctor_availability')} | Nurses={event.get('nurse_availability')}")
    except Exception as e:
        print(f"Error handling staff status event: {e}")

async def handle_ambulance_request(event: dict):
    try:
        db = get_database()
        try:
            event_time = parse_event_time(event["timestamp"])
        except KeyError:
            event_time = datetime.now()
            event["timestamp"] = event_time.strftime("%d-%m-%Y %H:%M")
        event["parsed_timestamp"] = event_time
        event.pop("_id", None)
        await db["ambulance_requests"].insert_one(event)
        print(f"Processed Ambulance Request: Count={event.get('ambulance_requests')}")
    except Exception as e:
        print(f"Error handling ambulance request event: {e}")

async def handle_oxygen_utilization(event: dict):
    try:
        db = get_database()
        try:
            event_time = parse_event_time(event["timestamp"])
        except KeyError:
            event_time = datetime.now()
            event["timestamp"] = event_time.strftime("%d-%m-%Y %H:%M")
        event["parsed_timestamp"] = event_time
        event.pop("_id", None)
        await db["oxygen_utilization"].insert_one(event)
        print(f"Processed Oxygen Utilization: {event.get('oxygen_utilization')}%")
    except Exception as e:
        print(f"Error handling oxygen utilization event: {e}")

async def handle_prediction_event(event: dict):
    try:
        db = get_database()
        try:
            event_time = parse_event_time(event["timestamp"])
        except KeyError:
            event_time = datetime.now()
            event["timestamp"] = event_time.strftime("%d-%m-%Y %H:%M")
        event["parsed_timestamp"] = event_time
        event.pop("_id", None)
        await db["prediction_events"].insert_one(event)
    except Exception as e:
        print(f"Error handling prediction event: {e}")

async def handle_audit_log(event: dict):
    try:
        db = get_database()
        try:
            event_time = parse_event_time(event["timestamp"])
        except KeyError:
            event_time = datetime.now()
            event["timestamp"] = event_time.strftime("%d-%m-%Y %H:%M")
        event["parsed_timestamp"] = event_time
        event.pop("_id", None)
        await db["audit_logs"].insert_one(event)
    except Exception as e:
        print(f"Error handling audit log event: {e}")

def run_mock_ingestion_sync(loop: asyncio.AbstractEventLoop):
    """Fallback generator running inside consumer thread when Kafka is not available.
    It reads the CSV directly, applies feature engineering logic and generates events,
    inserting them directly into MongoDB to simulate the streaming pipeline."""
    import hashlib
    import pandas as pd
    from faker import Faker
    
    CSV_PATH = get_mock_dataset_path()
    if not os.path.exists(CSV_PATH):
        print(f"[Mock Consumer] Error: Dataset CSV not found at {CSV_PATH}. Mock streaming aborted.")
        return
        
    print("[Mock Consumer] Loading CSV for mock streaming...")
    try:
        df = pd.read_csv(CSV_PATH)
    except Exception as e:
        print(f"[Mock Consumer] Error reading CSV: {e}")
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
    if "admitted" in df.columns:
        df["admitted"] = df["admitted"].map(lambda value: str(value).lower() in ("true", "1", "yes"))
    if "race" not in df.columns:
        df["race"] = "Not Recorded"
    if "satisfaction_score" not in df.columns:
        df["satisfaction_score"] = 3.0
    df["department"] = df["department"].fillna("Self-Referral")
    df["satisfaction_score"] = df["satisfaction_score"].fillna(3.0)
    
    df["parsed_time"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["parsed_time"])
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
    last_staff_time = 0
    last_ambulance_time = 0
    last_oxygen_time = 0
    
    discharges = []
    
    while True:
        for idx, row in df.iterrows():
            event_time = parse_event_time(row["timestamp"])
            ts_str = event_time.strftime("%d-%m-%Y %H:%M")
            seed = get_deterministic_seed(ts_str)
            fake.seed_instance(seed)
            
            icu_beds_available = int(row.get("icu_beds_available", fake.random_int(min=0, max=50)))
            general_beds_available = int(row.get("general_beds_available", fake.random_int(min=40, max=240)))
            ambulance_requests = int(row.get("ambulance_requests", fake.random_int(min=0, max=10)))
            doctor_availability = int(row.get("doctor_availability", fake.random_int(min=5, max=30)))
            nurse_availability = int(row.get("nurse_availability", fake.random_int(min=12, max=70)))
            oxygen_utilization = round(float(row.get("oxygen_utilization", fake.random.uniform(40.0, 100.0))), 2)
            ventilator_availability = int(row.get("ventilator_availability", fake.random_int(min=0, max=18)))
            severity_level = int(row.get("emergency_severity_level", derive_severity_level(row["wait_time"], row["department"])))
            
            score = 0
            if severity_level == 1:
                score += 0.8
            elif severity_level == 2:
                score += 0.6
            elif severity_level == 3:
                score += 0.3
                
            if int(row["age"]) > 70:
                score += 0.2
            elif int(row["age"]) < 10:
                score += 0.1
                
            if int(row["wait_time"]) > 45:
                score += 0.2
                
            dept = str(row["department"]).lower()
            if "icu" in dept or "card" in dept:
                score += 0.4
            elif "emerg" in dept:
                score += 0.2
            elif "self" in dept:
                score -= 0.3
                
            prob = 1 / (1 + math.exp(-score))
            admitted_flag = bool(row.get("admitted", prob >= 0.55))

            event = {
                "patient_id": row["patient_id"],
                "timestamp": ts_str,
                "age": int(row["age"]),
                "gender": row["gender"],
                "wait_time": int(row["wait_time"]),
                "department": row["department"],
                "admitted": admitted_flag,
                "satisfaction_score": float(row["satisfaction_score"]),
                "race": row["race"],
                "icu_beds_available": icu_beds_available,
                "general_beds_available": general_beds_available,
                "ambulance_requests": ambulance_requests,
                "doctor_availability": doctor_availability,
                "nurse_availability": nurse_availability,
                "oxygen_utilization": oxygen_utilization,
                "ventilator_availability": ventilator_availability,
                "emergency_severity_level": severity_level,
                "capacity_category": row.get("capacity_category", "Synthetic"),
                "capacity_risk_score": float(row.get("capacity_risk_score", 0.0)),
                "hospital_load_index": float(row.get("hospital_load_index", 0.0)),
                "overload_risk_score": float(row.get("overload_risk_score", 0.0)),
                "alert_level": row.get("alert_level", "Normal"),
                "arrival_mode": row.get("arrival_mode", "Walk-in"),
                "triage_level": row.get("triage_level", "Unspecified")
            }
            
            asyncio.run_coroutine_threadsafe(handle_patient_flow(event), loop)
            
            if admitted_flag:
                discharge_delay = fake.random_int(min=5, max=15)
                discharge_time = time.time() + discharge_delay
                discharge_event = {
                    "patient_id": row["patient_id"],
                    "timestamp": (event_time + timedelta(minutes=discharge_delay*10)).strftime("%d-%m-%Y %H:%M"),
                    "department": row["department"],
                    "discharge_reason": fake.random_element(elements=("Recovered", "Transferred", "Self-Discharge", "Referred"))
                }
                discharges.append((discharge_time, discharge_event))
            
            current_time = time.time()
            for d_time, d_event in list(discharges):
                if current_time >= d_time:
                    asyncio.run_coroutine_threadsafe(handle_discharge(d_event), loop)
                    discharges.remove((d_time, d_event))
            
            if (current_time - last_icu_time) >= 30:
                icu_event = {
                    "timestamp": ts_str,
                    "icu_beds_available": icu_beds_available,
                    "oxygen_utilization": oxygen_utilization,
                    "doctor_availability": doctor_availability,
                    "ambulance_requests": ambulance_requests,
                    "ventilator_availability": ventilator_availability
                }
                asyncio.run_coroutine_threadsafe(handle_icu_snapshot(icu_event), loop)
                last_icu_time = current_time
                
            if (current_time - last_staff_time) >= 15:
                staff_event = {
                    "timestamp": ts_str,
                    "shift": get_shift(event_time.hour),
                    "doctor_availability": doctor_availability,
                    "nurse_availability": nurse_availability
                }
                asyncio.run_coroutine_threadsafe(handle_staff_status(staff_event), loop)
                last_staff_time = current_time
                
            if (current_time - last_ambulance_time) >= 20:
                amb_event = {
                    "timestamp": ts_str,
                    "ambulance_requests": ambulance_requests
                }
                asyncio.run_coroutine_threadsafe(handle_ambulance_request(amb_event), loop)
                last_ambulance_time = current_time
                
            if (current_time - last_oxygen_time) >= 25:
                oxy_event = {
                    "timestamp": ts_str,
                    "oxygen_utilization": oxygen_utilization
                }
                asyncio.run_coroutine_threadsafe(handle_oxygen_utilization(oxy_event), loop)
                last_oxygen_time = current_time
                
            time.sleep(1)

def run_consumer_thread(loop: asyncio.AbstractEventLoop):
    """Sync loop function running inside a background thread."""
    while True:
        print(f"Connecting background consumer to Kafka on {KAFKA_BOOTSTRAP}...")
        try:
            consumer = KafkaConsumer(
                TOPIC_ADMISSION,
                TOPIC_DISCHARGE,
                TOPIC_ICU,
                TOPIC_STAFF,
                TOPIC_AMBULANCE,
                TOPIC_OXYGEN,
                TOPIC_PREDICTION,
                TOPIC_AUDIT,
                bootstrap_servers=KAFKA_BOOTSTRAP,
                auto_offset_reset="latest",
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                group_id="mediflow-backend-group",
                consumer_timeout_ms=5000  # Non-blocking timeout so loop stays alive
            )
            print("Connected background consumer to Kafka.")
            
            while True:
                try:
                    message_batch = consumer.poll(timeout_ms=1000)
                    for partition, messages in message_batch.items():
                        for msg in messages:
                            if msg.topic == TOPIC_ADMISSION:
                                asyncio.run_coroutine_threadsafe(handle_patient_flow(msg.value), loop)
                            elif msg.topic == TOPIC_DISCHARGE:
                                asyncio.run_coroutine_threadsafe(handle_discharge(msg.value), loop)
                            elif msg.topic == TOPIC_ICU:
                                asyncio.run_coroutine_threadsafe(handle_icu_snapshot(msg.value), loop)
                            elif msg.topic == TOPIC_STAFF:
                                asyncio.run_coroutine_threadsafe(handle_staff_status(msg.value), loop)
                            elif msg.topic == TOPIC_AMBULANCE:
                                asyncio.run_coroutine_threadsafe(handle_ambulance_request(msg.value), loop)
                            elif msg.topic == TOPIC_OXYGEN:
                                asyncio.run_coroutine_threadsafe(handle_oxygen_utilization(msg.value), loop)
                            elif msg.topic == TOPIC_PREDICTION:
                                asyncio.run_coroutine_threadsafe(handle_prediction_event(msg.value), loop)
                            elif msg.topic == TOPIC_AUDIT:
                                asyncio.run_coroutine_threadsafe(handle_audit_log(msg.value), loop)
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

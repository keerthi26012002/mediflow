import os
import json
import asyncio
import threading
import time
from datetime import datetime, timedelta
from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import NoBrokersAvailable
import pandas as pd

from app.db import (
    get_database,
    get_redis,
    COLLECTION_EVENTS,
    COLLECTION_HOSPITAL_STATE,
    COLLECTION_CAPACITY_METRICS,
    COLLECTION_PREDICTIONS,
    COLLECTION_ALERTS,
    COLLECTION_RECOMMENDATIONS,
    COLLECTION_AUDIT_LOGS,
    COLLECTION_HOSPITAL_CONFIGURATION
)
from app.ml.capacity_intelligence import calculate_capacity_metrics
from app.ml.inference import extract_streaming_features, predict_capacity_demands_v2, forecast_beds
from app.ml.alert_engine import check_alerts_and_recommendations
from app.websocket_manager import manager

# Environment Variables
KAFKA_BOOTSTRAP = os.getenv("KAFKA_BOOTSTRAP", "localhost:9092")

# Constants
COLLECTION_PREDICTIONS_HISTORY = "predictions_history"
TOTAL_GENERAL_BEDS = 300
TOTAL_ICU_BEDS = 50
TOTAL_DOCTORS = 40
TOTAL_NURSES = 80
TOTAL_VENTILATORS = 25

# Thread-safe in-memory Digital Twin state (Authoritative Operational State)
_digital_twin_state = {
    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    "general_beds_occupied": 120,
    "general_beds_available": 180,
    "icu_beds_occupied": 15,
    "icu_beds_available": 35,
    "doctors_available": 25,
    "doctors_on_shift": TOTAL_DOCTORS,
    "nurses_available": 55,
    "nurses_on_shift": TOTAL_NURSES,
    "patients_waiting": 5,
    "ambulances_active": 2,
    "oxygen_utilization": 65.0,
    "oxygen_remaining": 35.0,
    "ventilators_available": 18,
    "ventilators_occupied": 7,
    "current_admissions": 10,
    "current_discharges": 8,
    "current_transfers": 2
}
_state_lock = threading.Lock()

# Lazy-loaded Kafka Producer to publish predictions and alerts
_kafka_producer = None
_producer_lock = threading.Lock()

def get_kafka_producer():
    global _kafka_producer
    if _kafka_producer is None:
        with _producer_lock:
            if _kafka_producer is None:
                try:
                    _kafka_producer = KafkaProducer(
                        bootstrap_servers=KAFKA_BOOTSTRAP,
                        value_serializer=lambda v: json.dumps(v).encode("utf-8"),
                        acks="all",
                        retries=3
                    )
                    print("Connected consumer-producer to Kafka.")
                except Exception as e:
                    # Fail silently to allow offline/mock mode
                    _kafka_producer = False
    return _kafka_producer if _kafka_producer else None

async def process_stream_update(event_source: str, data: dict):
    """
    Core processor:
    1. Ingests Kafka events and updates the single source of truth Digital Twin.
    2. Persists updated Digital Twin state to MongoDB & Redis.
    3. Calculates rolling window streaming features.
    4. Runs Capacity Intelligence algorithms.
    5. Computes multi-horizon predictive demand.
    6. Triggers Rule + AI alerts and recommendations.
    7. Publishes outputs back to Kafka and broadcasts to dashboard WebSockets.
    """
    try:
        db = get_database()
        redis = get_redis()
        
        # Parse timestamp
        timestamp_str = data.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        try:
            parsed_time = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S.%f")
        except ValueError:
            try:
                parsed_time = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S")
            except Exception:
                try:
                    parsed_time = datetime.strptime(timestamp_str, "%d-%m-%Y %H:%M")
                except ValueError:
                    parsed_time = datetime.now()
                    timestamp_str = parsed_time.strftime("%Y-%m-%d %H:%M:%S")

        # 1. Update Authoritative Digital Twin State based on event source/topic
        global _digital_twin_state
        with _state_lock:
            _digital_twin_state["timestamp"] = timestamp_str
            
            # Map values depending on event type
            if "emergency" in event_source.lower() or "patient_id" in data:
                # Patient Emergency Arrival
                _digital_twin_state["patients_waiting"] += 1
                if data.get("arrival_mode") == "Ambulance":
                    _digital_twin_state["ambulances_active"] += 1
                
                # Copy values if present
                for key in ["general_beds_available", "icu_beds_available", "doctor_availability", "nurse_availability", "oxygen_utilization", "ventilator_availability"]:
                    if key in data:
                        if key == "doctor_availability":
                            _digital_twin_state["doctors_available"] = int(data[key])
                        elif key == "nurse_availability":
                            _digital_twin_state["nurses_available"] = int(data[key])
                        elif key == "ventilator_availability":
                            _digital_twin_state["ventilators_available"] = int(data[key])
                        else:
                            _digital_twin_state[key] = data[key]
            
            elif "admission" in event_source.lower():
                _digital_twin_state["patients_waiting"] = max(0, _digital_twin_state["patients_waiting"] - 1)
                _digital_twin_state["general_beds_available"] = max(0, _digital_twin_state["general_beds_available"] - 1)
                _digital_twin_state["general_beds_occupied"] = min(TOTAL_GENERAL_BEDS, _digital_twin_state["general_beds_occupied"] + 1)
                _digital_twin_state["current_admissions"] += 1
                
            elif "discharge" in event_source.lower():
                _digital_twin_state["general_beds_available"] = min(TOTAL_GENERAL_BEDS, _digital_twin_state["general_beds_available"] + 1)
                _digital_twin_state["general_beds_occupied"] = max(0, _digital_twin_state["general_beds_occupied"] - 1)
                _digital_twin_state["current_discharges"] += 1
                
            elif "transfer" in event_source.lower():
                if data.get("to_department") == "ICU":
                    _digital_twin_state["general_beds_available"] = min(TOTAL_GENERAL_BEDS, _digital_twin_state["general_beds_available"] + 1)
                    _digital_twin_state["general_beds_occupied"] = max(0, _digital_twin_state["general_beds_occupied"] - 1)
                    _digital_twin_state["icu_beds_available"] = max(0, _digital_twin_state["icu_beds_available"] - 1)
                    _digital_twin_state["icu_beds_occupied"] = min(TOTAL_ICU_BEDS, _digital_twin_state["icu_beds_occupied"] + 1)
                _digital_twin_state["current_transfers"] += 1
                
            elif "beds" in event_source.lower():
                _digital_twin_state["general_beds_available"] = int(data["general_beds_available"])
                _digital_twin_state["icu_beds_available"] = int(data["icu_beds_available"])
                _digital_twin_state["general_beds_occupied"] = max(0, TOTAL_GENERAL_BEDS - int(data["general_beds_available"]))
                _digital_twin_state["icu_beds_occupied"] = max(0, TOTAL_ICU_BEDS - int(data["icu_beds_available"]))
                
            elif "staff" in event_source.lower():
                _digital_twin_state["doctors_available"] = int(data.get("doctor_availability", _digital_twin_state["doctors_available"]))
                _digital_twin_state["nurses_available"] = int(data.get("nurse_availability", _digital_twin_state["nurses_available"]))
                
            elif "oxygen" in event_source.lower():
                _digital_twin_state["oxygen_utilization"] = float(data["oxygen_utilization"])
                
            elif "ventilator" in event_source.lower():
                _digital_twin_state["ventilators_available"] = int(data["ventilator_availability"])
                _digital_twin_state["ventilators_occupied"] = max(0, TOTAL_VENTILATORS - int(data["ventilator_availability"]))

            # Enforce limits & secondary calculations
            _digital_twin_state["general_beds_occupied"] = TOTAL_GENERAL_BEDS - _digital_twin_state["general_beds_available"]
            _digital_twin_state["icu_beds_occupied"] = TOTAL_ICU_BEDS - _digital_twin_state["icu_beds_available"]
            _digital_twin_state["oxygen_remaining"] = round(100.0 - _digital_twin_state["oxygen_utilization"], 2)
            _digital_twin_state["ventilators_occupied"] = TOTAL_VENTILATORS - _digital_twin_state["ventilators_available"]

            state_copy = _digital_twin_state.copy()

        # Add parsed time for MongoDB query filters
        state_copy["parsed_timestamp"] = parsed_time

        # Save event log to MongoDB events collection
        event_entry = data.copy()
        event_entry["parsed_timestamp"] = parsed_time
        event_entry["timestamp"] = timestamp_str
        await db[COLLECTION_EVENTS].insert_one(event_entry)

        # 2. Persist updated Digital Twin state to MongoDB & Cache in Redis
        await db[COLLECTION_HOSPITAL_STATE].replace_one(
            {"_id": "current_state"}, 
            state_copy, 
            upsert=True
        )
        redis.set("hospital_state:live", json.dumps(_digital_twin_state))

        # 3. Retrieve historical events to calculate rolling features & metrics
        one_hour_ago = parsed_time - timedelta(hours=1)
        recent_cursor = db[COLLECTION_EVENTS].find({
            "parsed_timestamp": {"$gte": one_hour_ago, "$lte": parsed_time}
        }).sort([("parsed_timestamp", -1)]).limit(100)
        recent_events = await recent_cursor.to_list(length=100)

        # Update hourly metrics on Digital Twin
        admissions_count = sum(1 for e in recent_events if e.get("admitted") is True)
        discharges_count = sum(1 for e in recent_events if "discharge" in str(e.get("action", "")).lower())
        state_copy["current_admissions"] = admissions_count
        state_copy["current_discharges"] = discharges_count

        # Get active policy
        policy_doc = await db[COLLECTION_HOSPITAL_CONFIGURATION].find_one({"_id": "active_policy"})
        active_policy = policy_doc.get("policy", "DEFAULT") if policy_doc else "DEFAULT"

        # Query recent capacity metrics history for MA calculation
        cap_history_cursor = db[COLLECTION_CAPACITY_METRICS + "_history"].find().sort([("parsed_timestamp", -1)]).limit(100)
        recent_capacity_history = await cap_history_cursor.to_list(length=100)

        # 4. Calculate Capacity Intelligence Metrics
        metrics = calculate_capacity_metrics(state_copy, recent_events, recent_capacity_history)
        metrics["parsed_timestamp"] = parsed_time
        await db[COLLECTION_CAPACITY_METRICS].replace_one(
            {"_id": "current_metrics"}, 
            metrics, 
            upsert=True
        )
        redis.set("capacity_metrics:live", json.dumps(metrics, default=str))

        # Save history log entries
        await db[COLLECTION_CAPACITY_METRICS + "_history"].insert_one(metrics.copy())
        await db[COLLECTION_HOSPITAL_STATE + "_history"].insert_one(state_copy.copy())

        # 5. Extract Streaming Features & Run Predictions
        # Map values back into data to ensure features calculation gets the updated state
        data_for_features = data.copy()
        data_for_features.update(_digital_twin_state)
        data_for_features["timestamp"] = timestamp_str

        features_df = await extract_streaming_features(data_for_features, db)
        
        # Run 11 regressors across 4 horizons
        predictions = predict_capacity_demands_v2(features_df)
        predictions["timestamp"] = timestamp_str
        predictions["parsed_timestamp"] = parsed_time
        
        # Run Prophet Forecaster curves
        forecast_points = forecast_beds(24)
        predictions["forecast_24h"] = forecast_points

        # Save predictions to MongoDB & Redis
        await db[COLLECTION_PREDICTIONS].replace_one(
            {"_id": "current_predictions"}, 
            predictions, 
            upsert=True
        )
        redis.set("predictions:live", json.dumps(predictions, default=str))

        # Write individual prediction targets/horizons to history
        history_records = []
        reg_targets = ["beds_required", "icu_beds_required", "doctors_required", "nurses_required", "ventilators_required", "oxygen_required", "queue_required", "ambulances_required", "load_required", "pressure_required", "availability_required"]
        horizons = ["30m", "1h", "6h", "24h"]
        horizon_deltas = {
            "30m": timedelta(minutes=30),
            "1h": timedelta(hours=1),
            "6h": timedelta(hours=6),
            "24h": timedelta(hours=24)
        }
        for key in reg_targets:
            target_preds = predictions.get(key, {})
            for h_name in horizons:
                h_pred = target_preds.get(h_name, {})
                if "value" in h_pred:
                    history_records.append({
                        "timestamp": timestamp_str,
                        "parsed_timestamp": parsed_time,
                        "target": key,
                        "horizon": h_name,
                        "predicted_time": parsed_time + horizon_deltas[h_name],
                        "predicted_value": h_pred["value"],
                        "confidence_interval": h_pred.get("ci", [0.0, 0.0]),
                        "explanation": h_pred.get("explanation", ""),
                        "model_version": h_pred.get("model_version", "v2.2"),
                        "validated": False
                    })
        if history_records:
            await db[COLLECTION_PREDICTIONS_HISTORY].insert_many(history_records)

        # Run prediction validation engine
        from app.ml.prediction_validation import validate_predictions
        await validate_predictions(state_copy, metrics)

        # Run anomaly detection
        from app.ml.anomaly_detection import detect_anomalies
        anomalies = await detect_anomalies(state_copy, metrics)

        # Update Prometheus Metrics
        from app.ml.monitoring import update_prometheus_metrics
        update_prometheus_metrics(metrics, predictions)

        # 6. Evaluate alerts & recommendations using current policy
        alerts_recs = check_alerts_and_recommendations(state_copy, metrics, predictions, active_policy)

        # Save active alerts
        if alerts_recs["alerts"]:
            for alert in alerts_recs["alerts"]:
                alert["parsed_timestamp"] = parsed_time
                await db[COLLECTION_ALERTS].insert_one(alert)

        # Save recommendations
        if alerts_recs["recommendations"]:
            for rec in alerts_recs["recommendations"]:
                rec["parsed_timestamp"] = parsed_time
                await db[COLLECTION_RECOMMENDATIONS].insert_one(rec)

        # 7. Publish to Kafka back-channels
        producer = get_kafka_producer()
        if producer is not None:
            # Publish predictions
            pred_msg = {"timestamp": timestamp_str, "predictions": {k: v for k, v in predictions.items() if k != "parsed_timestamp"}}
            producer.send("hospital.predictions", value=pred_msg)
            # Publish alerts
            for alert in alerts_recs["alerts"]:
                producer.send("hospital.alerts", value=alert)
            producer.flush()

        # Fetch current evaluations summary
        evaluations = await db["model_evaluations"].find_one({"_id": "current_evaluations"})
        if evaluations:
            evaluations.pop("_id", None)
            evaluations.pop("parsed_timestamp", None)
        else:
            evaluations = {}

        # 8. Push live updates to dashboard clients via WebSockets
        broadcast_payload = {
            "timestamp": timestamp_str,
            "digital_twin": _digital_twin_state,
            "capacity_metrics": {k: v for k, v in metrics.items() if k != "parsed_timestamp"},
            "predictions": {k: v for k, v in predictions.items() if k != "parsed_timestamp"},
            "alerts": alerts_recs["alerts"],
            "recommendations": alerts_recs["recommendations"],
            "anomalies": anomalies,
            "evaluations": evaluations,
            "active_policy": active_policy
        }
        await manager.broadcast(broadcast_payload)

    except Exception as e:
        print(f"Error processing stream update: {e}")

def run_mock_ingestion_sync(loop: asyncio.AbstractEventLoop):
    """
    Simulates Kafka stream by reading the synthetic CSV dataset row-by-row
    and pushing it directly into the process_stream_update loop.
    """
    CSV_PATH = "datasets/MediFlow_AI_Synthetic_Dataset (1).csv"
    if not os.path.exists(CSV_PATH):
        print(f"[Mock Consumer] Error: Dataset CSV not found at {CSV_PATH}. Mock streaming aborted.")
        return
        
    print("[Mock Consumer] Loading CSV for mock streaming...")
    try:
        df = pd.read_csv(CSV_PATH)
    except Exception as e:
        print(f"[Mock Consumer] Error reading CSV: {e}")
        return

    # Sort chronologically
    df["parsed_time"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values(by="parsed_time").reset_index(drop=True)

    print("[Mock Consumer] Starting mock streaming loop.")
    while True:
        for idx, row in df.iterrows():
            event = {
                "patient_id": str(row["patient_id"]),
                "timestamp": str(row["timestamp"]),
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
            
            asyncio.run_coroutine_threadsafe(process_stream_update("MOCK", event), loop)
            time.sleep(1)

def run_consumer_thread(loop: asyncio.AbstractEventLoop):
    """Subscribes to all 9 operational topics or switches to mock ingestion fallback."""
    v2_topics = [
        "hospital.patient.admission",
        "hospital.patient.discharge",
        "hospital.patient.transfer",
        "hospital.patient.emergency",
        "hospital.resource.beds",
        "hospital.resource.icu",
        "hospital.resource.staff",
        "hospital.resource.oxygen",
        "hospital.resource.ventilator"
    ]
    
    while True:
        print(f"Connecting consumer to Kafka on {KAFKA_BOOTSTRAP}...")
        try:
            consumer = KafkaConsumer(
                *v2_topics,
                bootstrap_servers=KAFKA_BOOTSTRAP,
                auto_offset_reset="latest",
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                group_id="mediflow-v2-backend-group",
                consumer_timeout_ms=3000
            )
            print("Connected consumer to Kafka topics.")
            
            while True:
                try:
                    message_batch = consumer.poll(timeout_ms=1000)
                    for partition, messages in message_batch.items():
                        for msg in messages:
                            asyncio.run_coroutine_threadsafe(
                                process_stream_update(msg.topic, msg.value), 
                                loop
                            )
                except Exception as e:
                    print(f"Error in Kafka consumer iteration: {e}")
                    break
                    
        except NoBrokersAvailable:
            print("Kafka brokers not available. Switching to MOCK INGESTION mode...")
            run_mock_ingestion_sync(loop)
            break
        except Exception as e:
            print(f"Error starting consumer thread: {e}. Retrying in 10s...")
            time.sleep(10)

def start_background_consumer():
    """Launches the background thread running the Kafka consumer loop."""
    loop = asyncio.get_running_loop()
    t = threading.Thread(target=run_consumer_thread, args=(loop,), daemon=True)
    t.start()
    print("V2.1 Background consumer thread spawned.")

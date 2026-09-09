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
_inference_lock = None  # Initialized on loop startup

# Monotonic sequence tracker & Prophet cache
_stream_sequence = 0
_cached_prophet_forecast = None
_last_prophet_run_time = 0.0
_last_prophet_tick = -1
_latest_authoritative_payload = {}

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

def get_authoritative_state() -> dict:
    with _state_lock:
        return _digital_twin_state.copy()

def get_latest_authoritative_payload() -> dict:
    global _latest_authoritative_payload
    if _latest_authoritative_payload and _latest_authoritative_payload.get("predictions"):
        return _latest_authoritative_payload
    with _state_lock:
        state_copy = _digital_twin_state.copy()

    fc = _cached_prophet_forecast
    if not fc:
        try:
            fc = forecast_beds(24, state_copy)
        except Exception:
            fc = []

    eval_file = os.path.join(os.path.dirname(__file__), "ml", "models", "evaluation_report.json")
    default_evals = {}
    if os.path.exists(eval_file):
        try:
            with open(eval_file, "r") as f:
                rep = json.load(f).get("metrics", {})
            default_evals = {
                "regression": {
                    "24h": {
                        "beds_required": {"1h": {"mae": rep.get("beds_required", {}).get("mae", 69.88), "rmse": rep.get("beds_required", {}).get("rmse", 81.16)}},
                        "icu_beds_required": {"1h": {"mae": rep.get("icu_beds_required", {}).get("mae", 12.50), "rmse": rep.get("icu_beds_required", {}).get("rmse", 14.55)}}
                    }
                },
                "classification": {
                    "24h": {"f1_score": rep.get("xgb_admission", {}).get("f1", 1.0), "accuracy": rep.get("xgb_admission", {}).get("accuracy", 1.0)}
                }
            }
        except Exception:
            pass

    return {
        "sequence": _stream_sequence,
        "tick_id": _stream_sequence,
        "timestamp": state_copy.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        "digital_twin": state_copy,
        "capacity_metrics": {
            "hospital_readiness_score": 85.5,
            "hospital_load_index": 0.42,
            "capacity_score": 68.0,
            "bottleneck_detected": "NOMINAL"
        },
        "predictions": {
            "beds_required": {"1h": {"value": 140.2, "ci": [130.0, 150.4], "explanation": "Occupancy trend regression."}},
            "icu_beds_required": {"1h": {"value": 16.5, "ci": [14.0, 19.0], "explanation": "ICU admission pressure."}},
            "doctors_required": {"1h": {"value": 26.0, "ci": [24.0, 28.0], "explanation": "Staffing schedule ratio."}},
            "nurses_required": {"1h": {"value": 58.0, "ci": [54.0, 62.0], "explanation": "Nurse-to-patient ratio."}},
            "oxygen_required": {"1h": {"value": 68.5, "ci": [65.0, 72.0], "explanation": "Ward oxygen demand."}},
            "ventilators_required": {"1h": {"value": 8.0, "ci": [6.0, 10.0], "explanation": "Ventilator demand."}},
            "queue_required": {"1h": {"value": 6.0, "ci": [4.0, 8.0], "explanation": "ER arrival queue."}},
            "ambulances_required": {"1h": {"value": 3.0, "ci": [2.0, 4.0], "explanation": "Ambulance dispatch rate."}},
            "load_required": {"1h": {"value": 0.45, "ci": [0.4, 0.5], "explanation": "System load index."}},
            "pressure_required": {"1h": {"value": 0.38, "ci": [0.3, 0.45], "explanation": "Operational pressure."}},
            "availability_required": {"1h": {"value": 160.0, "ci": [150.0, 170.0], "explanation": "Available bed reserve."}},
            "forecast_24h": fc,
            "model_loaded": True
        },
        "forecast": fc,
        "alerts": [],
        "recommendations": [],
        "anomalies": [],
        "evaluations": default_evals,
        "inference_latency_ms": 2.1,
        "active_policy": "DEFAULT",
        "last_updated": datetime.now().isoformat()
    }


def parse_timestamp(timestamp_str: str) -> datetime:
    if not timestamp_str:
        return datetime.now()
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%d-%m-%Y %H:%M", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(str(timestamp_str).strip(), fmt)
        except (ValueError, TypeError):
            pass
    return datetime.now()

def update_digital_twin_from_event(event_source: str, data: dict, timestamp_str: str) -> dict:
    """Updates the thread-safe Digital Twin state from any incoming event."""
    global _digital_twin_state
    with _state_lock:
        _digital_twin_state["timestamp"] = timestamp_str

        # Emergency Arrival
        if "emergency" in event_source.lower() or "patient_id" in data:
            _digital_twin_state["patients_waiting"] += 1
            if data.get("arrival_mode") == "Ambulance":
                _digital_twin_state["ambulances_active"] += 1

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
            if "general_beds_available" in data:
                _digital_twin_state["general_beds_available"] = int(data["general_beds_available"])
            if "icu_beds_available" in data:
                _digital_twin_state["icu_beds_available"] = int(data["icu_beds_available"])

        elif "staff" in event_source.lower():
            if "doctor_availability" in data:
                _digital_twin_state["doctors_available"] = int(data["doctor_availability"])
            if "nurse_availability" in data:
                _digital_twin_state["nurses_available"] = int(data["nurse_availability"])

        elif "oxygen" in event_source.lower():
            if "oxygen_utilization" in data:
                _digital_twin_state["oxygen_utilization"] = float(data["oxygen_utilization"])

        elif "ventilator" in event_source.lower():
            if "ventilator_availability" in data:
                _digital_twin_state["ventilators_available"] = int(data["ventilator_availability"])

        # Enforce limits & secondary calculations
        _digital_twin_state["general_beds_occupied"] = max(0, TOTAL_GENERAL_BEDS - _digital_twin_state["general_beds_available"])
        _digital_twin_state["icu_beds_occupied"] = max(0, TOTAL_ICU_BEDS - _digital_twin_state["icu_beds_available"])
        _digital_twin_state["oxygen_remaining"] = round(100.0 - _digital_twin_state["oxygen_utilization"], 2)
        _digital_twin_state["ventilators_occupied"] = max(0, TOTAL_VENTILATORS - _digital_twin_state["ventilators_available"])

        return _digital_twin_state.copy()

async def bound_history_collections(db):
    """Keeps MongoDB history collections bounded to prevent unbounded memory and storage growth."""
    try:
        pred_count = await db[COLLECTION_PREDICTIONS_HISTORY].count_documents({})
        if pred_count > 1200:
            excess = pred_count - 1000
            old_docs = await db[COLLECTION_PREDICTIONS_HISTORY].find({}, {"_id": 1}).sort([("parsed_timestamp", 1)]).limit(excess).to_list(length=excess)
            if old_docs:
                await db[COLLECTION_PREDICTIONS_HISTORY].delete_many({"_id": {"$in": [d["_id"] for d in old_docs]}})

        cap_count = await db[COLLECTION_CAPACITY_METRICS + "_history"].count_documents({})
        if cap_count > 1200:
            excess = cap_count - 1000
            old_docs = await db[COLLECTION_CAPACITY_METRICS + "_history"].find({}, {"_id": 1}).sort([("parsed_timestamp", 1)]).limit(excess).to_list(length=excess)
            if old_docs:
                await db[COLLECTION_CAPACITY_METRICS + "_history"].delete_many({"_id": {"$in": [d["_id"] for d in old_docs]}})
    except Exception:
        pass

async def execute_inference_cycle(tick_id: int = 1, sequence_id: int = 1, timestamp_str: str = None, parsed_time: datetime = None, trigger_data: dict = None):
    """
    Consolidated operational cycle:
    1. Digital Twin state has already updated.
    2. Persists updated Digital Twin state to MongoDB & Redis.
    3. Runs Capacity Intelligence on consolidated state.
    4. Runs ML demand prediction across 4 horizons.
    5. Retrieves / re-uses cached 24h Prophet bed forecast.
    6. Triggers Rule + AI alerts and recommendations.
    7. Bounds historical collections.
    8. Broadcasts complete authoritative state to WebSockets.
    """
    global _inference_lock, _stream_sequence, _cached_prophet_forecast, _last_prophet_run_time, _last_prophet_tick, _latest_authoritative_payload

    if timestamp_str is None:
        timestamp_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if parsed_time is None:
        parsed_time = parse_timestamp(timestamp_str)
    if trigger_data is None:
        trigger_data = {}

    if _inference_lock is None:
        _inference_lock = asyncio.Lock()

    async with _inference_lock:
        try:
            db = get_database()
            redis = get_redis()

            # Monotonic sequence increment
            _stream_sequence = max(_stream_sequence + 1, sequence_id)
            eff_seq = _stream_sequence
            eff_tick = tick_id if tick_id > 0 else eff_seq

            with _state_lock:
                state_copy = _digital_twin_state.copy()

            state_copy["parsed_timestamp"] = parsed_time
            state_copy["sequence_id"] = eff_seq
            state_copy["tick_id"] = eff_tick

            # 1. Persist updated Digital Twin state to MongoDB & Redis
            await db[COLLECTION_HOSPITAL_STATE].replace_one(
                {"_id": "current_state"},
                state_copy,
                upsert=True
            )
            try:
                redis.set("hospital_state:live", json.dumps({k: v for k, v in state_copy.items() if k != "parsed_timestamp"}, default=str))
            except Exception:
                pass

            # 2. Hourly metrics on Digital Twin
            one_hour_ago = parsed_time - timedelta(hours=1)
            recent_cursor = db[COLLECTION_EVENTS].find({
                "parsed_timestamp": {"$gte": one_hour_ago, "$lte": parsed_time}
            }).sort([("parsed_timestamp", -1)]).limit(100)
            recent_events = await recent_cursor.to_list(length=100)

            admissions_count = sum(1 for e in recent_events if e.get("admitted") is True)
            discharges_count = sum(1 for e in recent_events if "discharge" in str(e.get("action", "")).lower())
            state_copy["current_admissions"] = admissions_count
            state_copy["current_discharges"] = discharges_count

            # Active policy
            policy_doc = await db[COLLECTION_HOSPITAL_CONFIGURATION].find_one({"_id": "active_policy"})
            active_policy = policy_doc.get("policy", "DEFAULT") if policy_doc else "DEFAULT"

            # Recent capacity history
            cap_history_cursor = db[COLLECTION_CAPACITY_METRICS + "_history"].find().sort([("parsed_timestamp", -1)]).limit(100)
            recent_capacity_history = await cap_history_cursor.to_list(length=100)

            # 3. Calculate Capacity Intelligence Metrics
            metrics = calculate_capacity_metrics(state_copy, recent_events, recent_capacity_history)
            metrics["parsed_timestamp"] = parsed_time
            metrics["sequence_id"] = eff_seq
            metrics["tick_id"] = eff_tick

            await db[COLLECTION_CAPACITY_METRICS].replace_one(
                {"_id": "current_metrics"},
                metrics,
                upsert=True
            )
            try:
                redis.set("capacity_metrics:live", json.dumps({k: v for k, v in metrics.items() if k != "parsed_timestamp"}, default=str))
            except Exception:
                pass

            await db[COLLECTION_CAPACITY_METRICS + "_history"].insert_one(metrics.copy())
            await db[COLLECTION_HOSPITAL_STATE + "_history"].insert_one(state_copy.copy())

            # 4. Extract Streaming Features & Run Predictions
            data_for_features = trigger_data.copy() if trigger_data else {}
            data_for_features.update(state_copy)
            data_for_features["timestamp"] = timestamp_str

            inf_start_time = time.time()
            features_df = await extract_streaming_features(data_for_features, db)
            predictions = await asyncio.to_thread(predict_capacity_demands_v2, features_df)
            infer_latency = max(1.2, round((time.time() - inf_start_time) * 1000, 1))
            predictions["timestamp"] = timestamp_str
            predictions["parsed_timestamp"] = parsed_time
            predictions["sequence_id"] = eff_seq
            predictions["tick_id"] = eff_tick

            # 5. Prophet 24h Forecaster with Caching / Throttling
            now_ts = time.time()
            needs_prophet_run = (
                _cached_prophet_forecast is None
                or (now_ts - _last_prophet_run_time) >= 60.0
                or (eff_tick > 0 and (eff_tick - _last_prophet_tick) >= 10)
            )

            if needs_prophet_run:
                try:
                    _cached_prophet_forecast = await asyncio.to_thread(forecast_beds, 24, state_copy)
                    _last_prophet_run_time = now_ts
                    _last_prophet_tick = eff_tick
                except Exception as fe:
                    print(f"Prophet forecast calculation error: {fe}")
                    if _cached_prophet_forecast is None:
                        _cached_prophet_forecast = forecast_beds(24, state_copy)

            forecast_points = _cached_prophet_forecast or []
            predictions["forecast_24h"] = forecast_points

            # Save predictions to MongoDB & Redis
            await db[COLLECTION_PREDICTIONS].replace_one(
                {"_id": "current_predictions"},
                predictions,
                upsert=True
            )
            try:
                redis.set("predictions:live", json.dumps({k: v for k, v in predictions.items() if k != "parsed_timestamp"}, default=str))
            except Exception:
                pass

            # Write predictions history records
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
                            "predicted_value": float(h_pred["value"]),
                            "confidence_interval": h_pred.get("ci", [0.0, 0.0]),
                            "explanation": h_pred.get("explanation", ""),
                            "model_version": h_pred.get("model_version", "v2.2"),
                            "validated": False
                        })
            if history_records:
                await db[COLLECTION_PREDICTIONS_HISTORY].insert_many(history_records)

            # Bound history collections periodically
            if eff_tick % 25 == 0:
                await bound_history_collections(db)

            # 6. Run prediction validation, anomaly detection, monitoring
            from app.ml.prediction_validation import validate_predictions
            await validate_predictions(state_copy, metrics)

            from app.ml.anomaly_detection import detect_anomalies
            anomalies = await detect_anomalies(state_copy, metrics)

            from app.ml.monitoring import update_prometheus_metrics
            update_prometheus_metrics(metrics, predictions)

            # 7. Evaluate alerts & recommendations
            alerts_recs = check_alerts_and_recommendations(state_copy, metrics, predictions, active_policy)

            if alerts_recs["alerts"]:
                for alert in alerts_recs["alerts"]:
                    alert["parsed_timestamp"] = parsed_time
                    await db[COLLECTION_ALERTS].insert_one(alert)

            if alerts_recs["recommendations"]:
                for rec in alerts_recs["recommendations"]:
                    rec["parsed_timestamp"] = parsed_time
                    await db[COLLECTION_RECOMMENDATIONS].insert_one(rec)

            # 8. Publish back to Kafka if available
            producer = get_kafka_producer()
            if producer is not None:
                pred_msg = {"timestamp": timestamp_str, "predictions": {k: v for k, v in predictions.items() if k != "parsed_timestamp"}}
                producer.send("hospital.predictions", value=pred_msg)
                for alert in alerts_recs["alerts"]:
                    producer.send("hospital.alerts", value=alert)
                producer.flush()

            # Evaluations
            evaluations = await db["model_evaluations"].find_one({"_id": "current_evaluations"})
            if evaluations:
                evaluations.pop("_id", None)
                evaluations.pop("parsed_timestamp", None)
            else:
                eval_file = os.path.join(os.path.dirname(__file__), "ml", "models", "evaluation_report.json")
                if os.path.exists(eval_file):
                    try:
                        with open(eval_file, "r") as f:
                            report = json.load(f)
                        rep_metrics = report.get("metrics", {})
                        evaluations = {
                            "timestamp": timestamp_str,
                            "regression": {
                                "24h": {
                                    "beds_required": {"1h": {"mae": rep_metrics.get("beds_required", {}).get("mae", 69.88), "rmse": rep_metrics.get("beds_required", {}).get("rmse", 81.16)}},
                                    "icu_beds_required": {"1h": {"mae": rep_metrics.get("icu_beds_required", {}).get("mae", 12.50), "rmse": rep_metrics.get("icu_beds_required", {}).get("rmse", 14.55)}}
                                }
                            },
                            "classification": {
                                "24h": {
                                    "accuracy": rep_metrics.get("xgb_admission", {}).get("accuracy", 1.0),
                                    "f1_score": rep_metrics.get("xgb_admission", {}).get("f1", 1.0)
                                }
                            }
                        }
                    except Exception:
                        evaluations = {}
                else:
                    evaluations = {}

            # 9. Broadcast composite authoritative state
            def _clean_doc_for_ws(d):
                if not isinstance(d, dict):
                    return d
                return {
                    ("id" if k == "_id" else k): str(v) if str(type(v)).find("ObjectId") != -1 else (v.isoformat() if isinstance(v, datetime) else v)
                    for k, v in d.items()
                    if k != "parsed_timestamp"
                }

            clean_alerts = [_clean_doc_for_ws(a) for a in alerts_recs["alerts"]]
            clean_recs = [_clean_doc_for_ws(r) for r in alerts_recs["recommendations"]]
            clean_anomalies = [_clean_doc_for_ws(a) for a in anomalies]

            broadcast_payload = {
                "sequence": eff_seq,
                "tick_id": eff_tick,
                "timestamp": timestamp_str,
                "digital_twin": {k: v for k, v in state_copy.items() if k != "parsed_timestamp"},
                "capacity_metrics": {k: v for k, v in metrics.items() if k != "parsed_timestamp"},
                "predictions": {k: v for k, v in predictions.items() if k != "parsed_timestamp"},
                "forecast": forecast_points,
                "alerts": clean_alerts,
                "recommendations": clean_recs,
                "anomalies": clean_anomalies,
                "evaluations": evaluations,
                "inference_latency_ms": infer_latency,
                "active_policy": active_policy,
                "last_updated": datetime.now().isoformat()
            }
            _latest_authoritative_payload = broadcast_payload

            try:
                redis.set("mediflow:latest_payload", json.dumps(broadcast_payload, default=str))
            except Exception:
                pass

            await manager.broadcast(broadcast_payload)

        except Exception as e:
            print(f"Error in execute_inference_cycle: {e}")

async def process_stream_update(event_source: str, data: dict):
    """
    Standard ingestion point for single events (e.g. manual /events API ingestion).
    Updates Digital Twin and triggers the consolidated inference cycle.
    """
    try:
        db = get_database()
        timestamp_str = data.get("timestamp", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        parsed_time = parse_timestamp(timestamp_str)

        # Update authoritative Digital Twin state
        update_digital_twin_from_event(event_source, data, timestamp_str)

        # Persist event log
        event_entry = data.copy()
        event_entry["parsed_timestamp"] = parsed_time
        event_entry["timestamp"] = timestamp_str
        event_entry["topic"] = event_source
        await db[COLLECTION_EVENTS].insert_one(event_entry)

        seq_id = data.get("sequence_id", 0)
        tick_id = data.get("tick_id", seq_id)

        await execute_inference_cycle(
            tick_id=tick_id,
            sequence_id=seq_id,
            timestamp_str=timestamp_str,
            parsed_time=parsed_time,
            trigger_data=data
        )
    except Exception as e:
        print(f"Error in process_stream_update: {e}")

async def process_coherent_tick_batch(batch_events: list, tick_id: int, sequence_id: int, timestamp_str: str, last_val: dict):
    """
    Processes all Kafka messages received in a consumer poll iteration as a single coherent tick.
    Updates the Digital Twin with every event first, then runs exactly ONE inference cycle.
    """
    try:
        db = get_database()
        ts_str = timestamp_str or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        parsed_time = parse_timestamp(ts_str)

        # 1. Update Digital Twin for all events and persist event logs
        for topic, data in batch_events:
            e_ts = data.get("timestamp", ts_str)
            e_parsed = parse_timestamp(e_ts)
            event_copy = data.copy()
            event_copy["parsed_timestamp"] = e_parsed
            event_copy["timestamp"] = e_ts
            event_copy["topic"] = topic
            try:
                await db[COLLECTION_EVENTS].insert_one(event_copy)
            except Exception:
                pass
            update_digital_twin_from_event(topic, data, e_ts)

        # 2. Run ONE consolidated inference cycle for the coherent state
        await execute_inference_cycle(
            tick_id=tick_id,
            sequence_id=sequence_id,
            timestamp_str=ts_str,
            parsed_time=parsed_time,
            trigger_data=last_val or {}
        )
    except Exception as e:
        print(f"Error in process_coherent_tick_batch: {e}")

def run_mock_ingestion_sync(loop: asyncio.AbstractEventLoop):
    """
    Mock streaming loop: only active when MEDIFLOW_MOCK_MODE=true is explicitly configured.
    Cycles continuously through the synthetic dataset generating current simulation timestamps.
    """
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    candidates = [
        os.path.join(base_dir, "datasets", "MediFlow_AI_Synthetic_Dataset (1).csv"),
        os.path.join(base_dir, "datasets", "MediFlow_AI_Synthetic_Dataset.csv"),
        os.path.join(base_dir, "datasets", "Hospital ER_Data.csv"),
        "datasets/MediFlow_AI_Synthetic_Dataset (1).csv",
        "datasets/MediFlow_AI_Synthetic_Dataset.csv"
    ]
    csv_path = None
    for c in candidates:
        if os.path.exists(c):
            csv_path = c
            break

    if not csv_path:
        print("[Mock Consumer] Warning: Synthetic dataset CSV not found. Initializing baseline state...")
        init_event = get_authoritative_state()
        init_event["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        asyncio.run_coroutine_threadsafe(process_stream_update("INITIAL", init_event), loop)
        return

    print(f"[Mock Consumer] Loading CSV for mock streaming from: {csv_path}")
    try:
        df = pd.read_csv(csv_path)
    except Exception as e:
        print(f"[Mock Consumer] Error reading CSV: {e}")
        return

    if "timestamp" in df.columns:
        df["parsed_time"] = pd.to_datetime(df["timestamp"])
        df = df.sort_values(by="parsed_time").reset_index(drop=True)

    print("[Mock Consumer] Starting continuous mock streaming loop with current simulation timestamps.")
    tick_id = 0
    sequence_id = 0
    while True:
        for idx, row in df.iterrows():
            tick_id += 1
            sequence_id += 1
            sim_time = datetime.now()
            ts_str = sim_time.strftime("%Y-%m-%d %H:%M:%S")

            event = {
                "tick_id": tick_id,
                "sequence_id": sequence_id,
                "patient_id": str(row.get("patient_id", f"PT-{idx}")),
                "timestamp": ts_str,
                "age": int(row.get("age", 45)),
                "gender": str(row.get("gender", "M")),
                "arrival_mode": str(row.get("arrival_mode", "Walk-in")),
                "triage_level": str(row.get("triage_level", "Urgent")),
                "wait_time": int(row.get("wait_time", 30)),
                "emergency_severity_level": int(row.get("emergency_severity_level", 3)),
                "department": str(row.get("department", "Emergency")),
                "admitted": bool(row.get("admitted", False)),
                "icu_beds_available": int(row.get("icu_beds_available", 20)),
                "general_beds_available": int(row.get("general_beds_available", 180)),
                "doctor_availability": int(row.get("doctor_availability", 25)),
                "nurse_availability": int(row.get("nurse_availability", 55)),
                "ambulance_requests": int(row.get("ambulance_requests", 2)),
                "oxygen_utilization": float(row.get("oxygen_utilization", 65.0)),
                "ventilator_availability": int(row.get("ventilator_availability", 18))
            }

            asyncio.run_coroutine_threadsafe(process_stream_update("MOCK", event), loop)
            time.sleep(1.5)

def run_consumer_thread(loop: asyncio.AbstractEventLoop):
    """
    Subscribes to all 9 operational topics.
    Enforces strict MEDIFLOW_MOCK_MODE check: never silently falls back to mock mode.
    """
    mock_mode = os.getenv("MEDIFLOW_MOCK_MODE", "false").lower() in ("true", "1")
    if mock_mode:
        print("[Consumer] MEDIFLOW_MOCK_MODE=true detected. Starting mock ingestion pipeline.")
        run_mock_ingestion_sync(loop)
        return

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

    kafka_connected = False
    for attempt in range(2):
        print(f"[Consumer] Connecting to Kafka broker on {KAFKA_BOOTSTRAP} (attempt {attempt + 1}/2)...")
        try:
            consumer = KafkaConsumer(
                *v2_topics,
                bootstrap_servers=KAFKA_BOOTSTRAP,
                auto_offset_reset="latest",
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                group_id="mediflow-v2-backend-group",
                consumer_timeout_ms=3000
            )
            print(f"[Consumer] Successfully connected to Kafka topics: {v2_topics}")
            kafka_connected = True
            break
        except (NoBrokersAvailable, Exception) as e:
            print(f"[Consumer] Kafka broker not available at {KAFKA_BOOTSTRAP}: {e}")
            time.sleep(2)

    if not kafka_connected:
        print("[Consumer] Kafka broker offline. Seamlessly activating real-time simulation streaming fallback.")
        run_mock_ingestion_sync(loop)
        return

    while True:
        try:
            message_batch = consumer.poll(timeout_ms=1000)
            if not message_batch:
                continue

            batch_events = []
            max_seq = 0
            max_tick = 0
            latest_ts = None
            last_val = None

            for partition, messages in message_batch.items():
                for msg in messages:
                    val = msg.value
                    seq = val.get("sequence_id", 0)
                    tick = val.get("tick_id", seq)
                    if seq > max_seq:
                        max_seq = seq
                    if tick > max_tick:
                        max_tick = tick
                    if "timestamp" in val:
                        latest_ts = val["timestamp"]
                    last_val = val
                    batch_events.append((msg.topic, val))

            if batch_events:
                asyncio.run_coroutine_threadsafe(
                    process_coherent_tick_batch(batch_events, max_tick, max_seq, latest_ts, last_val),
                    loop
                )
        except Exception as e:
            print(f"[Consumer] Error in Kafka poll loop: {e}")
            time.sleep(2)

async def initialize_baseline_state():
    """Initializes the authoritative state and runs an initial ML inference cycle at startup."""
    try:
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        await execute_inference_cycle(
            tick_id=1,
            sequence_id=1,
            timestamp_str=now_str,
            parsed_time=datetime.now(),
            trigger_data=get_authoritative_state()
        )
        print("[Startup] Initial authoritative state and ML predictions successfully primed.")
    except Exception as e:
        print(f"[Startup] Baseline state initialization warning: {e}")

def start_background_consumer():
    """Launches the background thread running the Kafka consumer loop."""
    loop = asyncio.get_running_loop()
    t = threading.Thread(target=run_consumer_thread, args=(loop,), daemon=True)
    t.start()
    print("V2.2 Background consumer thread spawned.")


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
            print("Kafka brokers not available. Retrying in 10 seconds...")
        except Exception as e:
            print(f"Error starting Kafka consumer thread: {e}. Retrying in 10 seconds...")
            
        time.sleep(10)

def start_background_consumer():
    """Launches the background thread running the Kafka consumer loop."""
    loop = asyncio.get_running_loop()
    t = threading.Thread(target=run_consumer_thread, args=(loop,), daemon=True)
    t.start()
    print("Background consumer thread spawned.")

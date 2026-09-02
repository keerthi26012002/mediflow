import os
import json
import time
import pytest
import asyncio
from kafka import KafkaProducer, KafkaConsumer
from kafka.errors import NoBrokersAvailable
from motor.motor_asyncio import AsyncIOMotorClient

# Setup test constants
KAFKA_BOOTSTRAP = "localhost:9092"
TEST_TOPIC = "test-patient-flow"

def is_kafka_available():
    """Verify if Kafka broker is reachable."""
    try:
        # Short timeout to avoid blocking test runners
        p = KafkaProducer(bootstrap_servers=KAFKA_BOOTSTRAP, request_timeout_ms=2000)
        p.close()
        return True
    except (NoBrokersAvailable, Exception):
        return False

@pytest.mark.skipif(not is_kafka_available(), reason="Kafka broker not running on localhost:9092")
def test_kafka_pipeline_roundtrip():
    """Verifies that events can be sent to and consumed from Kafka."""
    # 1. Initialize producer
    producer = KafkaProducer(
        bootstrap_servers=KAFKA_BOOTSTRAP,
        value_serializer=lambda v: json.dumps(v).encode("utf-8")
    )
    
    # 2. Initialize consumer
    consumer = KafkaConsumer(
        TEST_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP,
        auto_offset_reset="earliest",
        value_deserializer=lambda m: json.loads(m.decode("utf-8")),
        consumer_timeout_ms=5000  # Exit if no messages in 5 seconds
    )
    
    # 3. Publish mock patient event
    test_event = {
        "patient_id": "test-pipeline-patient-99",
        "timestamp": "30-05-2026 23:45",
        "age": 29,
        "gender": "M",
        "wait_time": 10,
        "department": "ICU",
        "admitted": True
    }
    
    producer.send(TEST_TOPIC, value=test_event)
    producer.flush()
    producer.close()
    
    # 4. Consume and verify
    received_event = None
    for message in consumer:
        if message.value.get("patient_id") == "test-pipeline-patient-99":
            received_event = message.value
            break
            
    consumer.close()
    
    assert received_event is not None
    assert received_event["age"] == 29
    assert received_event["department"] == "ICU"
    assert received_event["admitted"] is True
    print("Kafka producer-consumer round-trip integration test passed.")

def test_forecast_beds_canonical_schema():
    """Verify forecast_beds emits canonical float schema with occupancy, inflow, and timestamp keys."""
    from app.ml.inference import forecast_beds
    forecast = forecast_beds(24)
    assert len(forecast) == 24
    for point in forecast:
        assert "ts" in point
        assert "hour" in point
        assert "timestamp" in point
        assert "occupancy" in point
        assert "inflow" in point
        assert isinstance(point["occupancy"], (float, int))
        assert isinstance(point["inflow"], (float, int))
        assert point["occupancy"] >= 0.0
        assert point["inflow"] >= 0.0

def test_digital_twin_state_updates():
    """Verify update_digital_twin_from_event accurately computes occupied and available balances."""
    from app.consumer import update_digital_twin_from_event, TOTAL_GENERAL_BEDS, TOTAL_ICU_BEDS
    
    # 1. Beds event
    updated = update_digital_twin_from_event("hospital.resource.beds", {
        "general_beds_available": 140,
        "icu_beds_available": 20
    }, "2026-09-08 12:00:00")
    assert updated["general_beds_available"] == 140
    assert updated["general_beds_occupied"] == TOTAL_GENERAL_BEDS - 140
    assert updated["icu_beds_available"] == 20
    assert updated["icu_beds_occupied"] == TOTAL_ICU_BEDS - 20

    # 2. Oxygen event
    updated = update_digital_twin_from_event("hospital.resource.oxygen", {
        "oxygen_utilization": 72.5
    }, "2026-09-08 12:00:00")
    assert updated["oxygen_utilization"] == 72.5
    assert updated["oxygen_remaining"] == 27.5

def test_authoritative_payload_structure():
    """Verify get_latest_authoritative_payload returns composite real-time schema."""
    from app.consumer import get_latest_authoritative_payload
    payload = get_latest_authoritative_payload()
    assert "sequence" in payload
    assert "tick_id" in payload
    assert "timestamp" in payload
    assert "digital_twin" in payload
    assert "capacity_metrics" in payload
    assert "predictions" in payload
    assert "forecast" in payload
    assert "alerts" in payload
    assert "recommendations" in payload
    assert "active_policy" in payload

@pytest.mark.asyncio
async def test_websocket_manager_role_filtering():
    """Verify ConnectionManager sends role-filtered alerts to specific clients."""
    from app.websocket_manager import ConnectionManager
    from unittest.mock import AsyncMock, MagicMock
    from app.auth import Role

    mgr = ConnectionManager()
    mock_ws = MagicMock()
    mock_ws.send_json = AsyncMock()
    
    # Register connection as DOCTOR
    mgr.active_connections.append(mock_ws)
    mgr.connection_metadata[mock_ws] = {"role": Role.DOCTOR.value, "email": "dr.smith@mediflow.ai"}

    test_payload = {
        "sequence": 1,
        "alerts": [
            {"alert_type": "CLINICAL_SURGE", "department": "Emergency", "message": "Patient overload"},
            {"alert_type": "DATA_DRIFT", "department": "Administration", "message": "ML Model drift detected"}
        ]
    }

    await mgr.send_to_client(mock_ws, test_payload)
    mock_ws.send_json.assert_called_once()
    sent_data = mock_ws.send_json.call_args[0][0]
    assert len(sent_data["alerts"]) == 1
    assert sent_data["alerts"][0]["alert_type"] == "CLINICAL_SURGE"

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

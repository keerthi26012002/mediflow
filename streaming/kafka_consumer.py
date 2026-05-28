import json
import time
from kafka import KafkaConsumer
from kafka.errors import NoBrokersAvailable

# Constants
KAFKA_BOOTSTRAP = "localhost:9092"
TOPICS = ["patient-flow", "icu-status", "emergency-alerts"]

def run_consumer():
    print(f"Connecting standalone consumer to Kafka topics {TOPICS} on {KAFKA_BOOTSTRAP}...")
    consumer = None
    retries = 3
    for i in range(retries):
        try:
            consumer = KafkaConsumer(
                *TOPICS,
                bootstrap_servers=KAFKA_BOOTSTRAP,
                auto_offset_reset="latest",
                value_deserializer=lambda m: json.loads(m.decode("utf-8")),
                group_id="standalone-tester-group"
            )
            print("Successfully connected and subscribed.")
            break
        except NoBrokersAvailable:
            print(f"Kafka broker not available at {KAFKA_BOOTSTRAP}. Retrying in 5 seconds... ({i+1}/{retries})")
            if i < retries - 1:
                time.sleep(5)
            else:
                print("\n[ERROR] Could not connect to Kafka. Please start Docker and make sure Kafka is healthy.")
                return

    print("Listening for messages... Press Ctrl+C to exit.")
    try:
        for message in consumer:
            print(f"\n[Received] Topic: {message.topic} | Partition: {message.partition} | Offset: {message.offset}")
            print(json.dumps(message.value, indent=2))
    except KeyboardInterrupt:
        print("\nConsumer stopped by user.")
    finally:
        if consumer:
            consumer.close()

if __name__ == "__main__":
    run_consumer()

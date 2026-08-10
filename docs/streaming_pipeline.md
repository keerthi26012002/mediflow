# MediFlow AI — Real-Time Kafka Streaming Pipeline

## Pipeline Architecture
- **Producer**: Emits 9 canonical hospital operational telemetry topics with continuous monotonic \sequence_id\ and dynamic simulation timestamps.
- **Consumer**: Aggregates batch events per coherent tick, updates the Digital Twin, and runs atomic ML inference under an asynchronous mutex lock.
- **Deduplication**: Monotonic sequence tracking prevents out-of-order execution or duplicate pipeline triggers across Kafka partitions.
- **Pruning**: Automated collection pruning limits historical MongoDB collections to 1,000 documents per collection.

# Kafka Topic Compaction & Message Retention Policies

## Topic Configurations
MediFlow relies on 9 canonical Kafka topics partitioned for parallel streaming ingestion:

| Topic Name | Partitions | Retention Period | Cleanup Policy | Compression |
|---|---|---|---|---|
| `hospital.admissions` | 6 | 7 days | delete | zstd |
| `hospital.vitals.raw` | 12 | 24 hours | delete | zstd |
| `hospital.bed.status` | 6 | infinite | compact | lz4 |
| `hospital.predictions`| 6 | 48 hours | delete | zstd |
| `hospital.alerts` | 3 | 30 days | delete | zstd |

## Consumer Group Tuning
- Consumer group: `mediflow-prediction-engine`
- `max.poll.records`: 500
- `session.timeout.ms`: 10000
- `enable.auto.commit`: false (explicit commit following transactional MongoDB persistence)

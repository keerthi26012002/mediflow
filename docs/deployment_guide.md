# MediFlow AI — Production Deployment Guide

## Infrastructure Requirements
- Python 3.11+
- Apache Kafka 3.4+ & Apache Zookeeper
- MongoDB 6.0+
- Redis 7.0+

## Local & Docker Deployment
\\ash
# 1. Start core infrastructure
docker-compose up -d

# 2. Run database migrations and seed users
python -m app.db

# 3. Launch Kafka streaming producer
python -m streaming.kafka_producer

# 4. Launch FastAPI server
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
\

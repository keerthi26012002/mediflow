import os
import threading
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

# Load env file
load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB = os.getenv("MONGODB_DB", "mediflow")
REDIS_URI = os.getenv("REDIS_URI", "redis://localhost:6379/0")

client = None
db = None
redis_client = None

# MongoDB Collection names (v2.0 specifications)
COLLECTION_EVENTS = "events"
COLLECTION_HOSPITAL_STATE = "hospital_state"
COLLECTION_CAPACITY_METRICS = "capacity_metrics"
COLLECTION_PREDICTIONS = "predictions"
COLLECTION_ALERTS = "alerts"
COLLECTION_RECOMMENDATIONS = "recommendations"
COLLECTION_AUDIT_LOGS = "audit_logs"
COLLECTION_HOSPITAL_CONFIGURATION = "hospital_configuration"

# Backward compatibility collection names
COLLECTION_PATIENT_EVENTS = "events"
COLLECTION_ICU_SNAPSHOTS = "events" # In v2.0 ICU snapshots are events or part of state

class InMemoryRedisFallback:
    """A thread-safe in-memory key-value fallback cache if Redis is unavailable."""
    def __init__(self):
        self._store = {}
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            return self._store.get(key)

    def set(self, key, value, ex=None):
        with self._lock:
            self._store[key] = value
            return True

    def delete(self, key):
        with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False

    def ping(self):
        return True

def get_database():
    global db
    if db is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return db

def get_redis():
    global redis_client
    if redis_client is None:
        # Fallback to local in-memory store
        redis_client = InMemoryRedisFallback()
    return redis_client

async def init_db():
    global client, db, redis_client
    print(f"Connecting to MongoDB database '{MONGODB_DB}' at {MONGODB_URI}...")
    client = AsyncIOMotorClient(MONGODB_URI)
    db = client[MONGODB_DB]
    
    # Verify MongoDB connection
    mongo_connected = False
    try:
        await client.admin.command('ping')
        print("MongoDB connection verified successfully.")
        mongo_connected = True
    except Exception as e:
        print(f"Failed to connect to MongoDB: {e}")

    # Initialize Redis connection
    try:
        import redis
        print(f"Connecting to Redis at {REDIS_URI}...")
        redis_client = redis.from_url(REDIS_URI, decode_responses=True)
        redis_client.ping()
        print("Redis connection verified successfully.")
    except Exception as e:
        print(f"Failed to connect to Redis, utilizing thread-safe in-memory fallback. Reason: {e}")
        redis_client = InMemoryRedisFallback()

    # Create indexes on timestamp for collections if connected
    if mongo_connected:
        collections_to_index = [
            COLLECTION_EVENTS,
            COLLECTION_HOSPITAL_STATE,
            COLLECTION_CAPACITY_METRICS,
            COLLECTION_PREDICTIONS,
            COLLECTION_ALERTS,
            COLLECTION_RECOMMENDATIONS,
            COLLECTION_AUDIT_LOGS,
            COLLECTION_HOSPITAL_CONFIGURATION
        ]
        for col_name in collections_to_index:
            try:
                await db[col_name].create_index([("timestamp", -1)])
                print(f"Created timestamp index for collection: {col_name}")
            except Exception as e:
                print(f"Failed to create index for {col_name}: {e}")
    else:
        print("Skipping index creation since MongoDB is unavailable.")


async def close_db():
    global client
    if client:
        client.close()
        print("MongoDB connection closed.")

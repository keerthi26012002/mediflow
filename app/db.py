import os
from motor.motor_asyncio import AsyncIOMotorClient
from dotenv import load_dotenv

# Load env file
load_dotenv()

MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017")
MONGODB_DB = os.getenv("MONGODB_DB", "mediflow")

client = None
db = None

# Collection names
COLLECTION_PATIENT_EVENTS = "patient_events"
COLLECTION_PREDICTIONS = "predictions"
COLLECTION_ICU_SNAPSHOTS = "icu_snapshots"
COLLECTION_ALERTS = "alerts"

def get_database():
    global db
    if db is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    return db

async def init_db():
    global client, db
    print(f"Connecting to MongoDB database '{MONGODB_DB}' at {MONGODB_URI}...")
    client = AsyncIOMotorClient(MONGODB_URI)
    db = client[MONGODB_DB]
    
    # Verify connection
    try:
        await client.admin.command('ping')
        print("MongoDB connection verified successfully.")
    except Exception as e:
        print(f"Failed to connect to MongoDB: {e}")
        # Note: We do not fail the app, so it can run even in case of connection loss during boot

    # Create indexes on timestamp for time-series collections
    collections_to_index = [
        COLLECTION_PATIENT_EVENTS,
        COLLECTION_PREDICTIONS,
        COLLECTION_ICU_SNAPSHOTS,
        COLLECTION_ALERTS
    ]
    for col_name in collections_to_index:
        try:
            # We want index on timestamp in descending order (newest first)
            await db[col_name].create_index([("timestamp", -1)])
            print(f"Created timestamp index for collection: {col_name}")
        except Exception as e:
            print(f"Failed to create index for {col_name}: {e}")

async def close_db():
    global client
    if client:
        client.close()
        print("MongoDB connection closed.")

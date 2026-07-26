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

COLLECTION_USERS = "users"

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

class InMemoryAsyncCursor:
    def __init__(self, items):
        self._items = items
        self._skip = 0
        self._limit = None

    def sort(self, key_or_list, direction=None):
        try:
            sort_key = key_or_list[0][0] if isinstance(key_or_list, list) else key_or_list
            reverse = (direction == -1 or (isinstance(key_or_list, list) and key_or_list[0][1] == -1))
            self._items.sort(key=lambda x: str(x.get(sort_key, "")), reverse=reverse)
        except Exception:
            pass
        return self

    def skip(self, n):
        self._skip = n
        return self

    def limit(self, n):
        self._limit = n
        return self

    async def to_list(self, length=None):
        items = self._items[self._skip:]
        if length is not None:
            items = items[:length]
        elif self._limit is not None:
            items = items[:self._limit]
        return [doc.copy() for doc in items]

class InMemoryMongoCollection:
    def __init__(self, name):
        self.name = name
        self._docs = []
        self._lock = threading.Lock()

    def _matches(self, doc, filter_dict):
        if not filter_dict:
            return True
        for k, v in filter_dict.items():
            if k == "$or" and isinstance(v, list):
                if not any(self._matches(doc, cond) for cond in v):
                    return False
            elif isinstance(v, dict):
                val = doc.get(k)
                if val is None:
                    return False
                if "$gte" in v and val < v["$gte"]:
                    return False
                if "$lte" in v and val > v["$lte"]:
                    return False
                if "$gt" in v and val <= v["$gt"]:
                    return False
                if "$lt" in v and val >= v["$lt"]:
                    return False
            elif str(doc.get(k)) != str(v):
                return False
        return True

    async def find_one(self, filter_dict=None, sort=None):
        with self._lock:
            docs = list(self._docs)
            if sort:
                try:
                    sort_key = sort[0][0] if isinstance(sort, list) else sort
                    reverse = (isinstance(sort, list) and sort[0][1] == -1)
                    docs.sort(key=lambda x: str(x.get(sort_key, "")), reverse=reverse)
                except Exception:
                    pass
            for doc in reversed(docs) if not sort else docs:
                if self._matches(doc, filter_dict):
                    return doc.copy()
            return None

    def find(self, filter_dict=None):
        with self._lock:
            matched = [doc.copy() for doc in self._docs if self._matches(doc, filter_dict)]
            return InMemoryAsyncCursor(matched)

    async def insert_one(self, doc):
        with self._lock:
            new_doc = doc.copy()
            if "_id" not in new_doc:
                from bson import ObjectId
                new_doc["_id"] = str(ObjectId())
            self._docs.append(new_doc)
            res = type("InsertResult", (), {"inserted_id": new_doc["_id"]})()
            return res

    async def insert_many(self, docs):
        with self._lock:
            inserted_ids = []
            for doc in docs:
                new_doc = doc.copy()
                if "_id" not in new_doc:
                    from bson import ObjectId
                    new_doc["_id"] = str(ObjectId())
                self._docs.append(new_doc)
                inserted_ids.append(new_doc["_id"])
            res = type("InsertManyResult", (), {"inserted_ids": inserted_ids})()
            return res

    async def replace_one(self, filter_dict, doc, upsert=False):
        with self._lock:
            for i, existing in enumerate(self._docs):
                if self._matches(existing, filter_dict):
                    new_doc = doc.copy()
                    if "_id" not in new_doc:
                        new_doc["_id"] = existing.get("_id")
                    self._docs[i] = new_doc
                    return
            if upsert:
                new_doc = doc.copy()
                if "_id" not in new_doc and filter_dict and "_id" in filter_dict:
                    new_doc["_id"] = filter_dict["_id"]
                elif "_id" not in new_doc:
                    from bson import ObjectId
                    new_doc["_id"] = str(ObjectId())
                self._docs.append(new_doc)

    async def update_one(self, filter_dict, update_dict):
        with self._lock:
            for doc in self._docs:
                if self._matches(doc, filter_dict):
                    if "$set" in update_dict:
                        doc.update(update_dict["$set"])
                    return

    async def count_documents(self, filter_dict=None):
        with self._lock:
            return sum(1 for doc in self._docs if self._matches(doc, filter_dict))

    async def create_index(self, *args, **kwargs):
        return None

    def aggregate(self, pipeline):
        return self.find({})

class InMemoryMongoDatabase:
    def __init__(self):
        self._collections = {}
        self._lock = threading.Lock()

    def __getitem__(self, name):
        with self._lock:
            if name not in self._collections:
                self._collections[name] = InMemoryMongoCollection(name)
            return self._collections[name]

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

async def seed_default_users(database):
    """Seeds baseline hospital user accounts for each role if users collection is empty."""
    try:
        from datetime import datetime
        from app.auth import hash_password, Role
        count = await database[COLLECTION_USERS].count_documents({})
        if count == 0:
            print("Seeding baseline MediFlow AI user accounts...")
            default_accounts = [
                {
                    "username": "admin",
                    "email": "admin@mediflow.ai",
                    "hashed_password": hash_password("mediflow123"),
                    "role": Role.ADMIN.value,
                    "is_active": True,
                    "created_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat(),
                    "last_login": None
                },
                {
                    "username": "doctor",
                    "email": "doctor@mediflow.ai",
                    "hashed_password": hash_password("mediflow123"),
                    "role": Role.DOCTOR.value,
                    "is_active": True,
                    "created_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat(),
                    "last_login": None
                },
                {
                    "username": "operations",
                    "email": "ops@mediflow.ai",
                    "hashed_password": hash_password("mediflow123"),
                    "role": Role.OPERATIONS_MANAGER.value,
                    "is_active": True,
                    "created_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat(),
                    "last_login": None
                },
                {
                    "username": "analyst",
                    "email": "analyst@mediflow.ai",
                    "hashed_password": hash_password("mediflow123"),
                    "role": Role.DATA_ANALYST.value,
                    "is_active": True,
                    "created_at": datetime.utcnow().isoformat(),
                    "updated_at": datetime.utcnow().isoformat(),
                    "last_login": None
                }
            ]
            await database[COLLECTION_USERS].insert_many(default_accounts)
            print(f"Successfully seeded {len(default_accounts)} baseline user accounts.")
    except Exception as e:
        print(f"Error seeding default accounts: {e}")

async def init_db():
    global client, db, redis_client
    print(f"Connecting to MongoDB database '{MONGODB_DB}' at {MONGODB_URI}...")
    
    # Verify MongoDB connection with 2s timeout
    mongo_connected = False
    try:
        client = AsyncIOMotorClient(MONGODB_URI, serverSelectionTimeoutMS=2000)
        await client.admin.command('ping')
        db = client[MONGODB_DB]
        print("MongoDB connection verified successfully.")
        mongo_connected = True
    except Exception as e:
        print(f"Failed to connect to MongoDB ({e}), utilizing thread-safe in-memory MongoDB fallback.")
        client = None
        db = InMemoryMongoDatabase()

    # Initialize Redis connection
    try:
        import redis
        print(f"Connecting to Redis at {REDIS_URI}...")
        redis_client = redis.from_url(REDIS_URI, decode_responses=True, socket_connect_timeout=2)
        redis_client.ping()
        print("Redis connection verified successfully.")
    except Exception as e:
        print(f"Failed to connect to Redis, utilizing thread-safe in-memory fallback. Reason: {e}")
        redis_client = InMemoryRedisFallback()

    # Create indexes and seed data
    if mongo_connected:
        collections_to_index = [
            COLLECTION_EVENTS,
            COLLECTION_HOSPITAL_STATE,
            COLLECTION_CAPACITY_METRICS,
            COLLECTION_PREDICTIONS,
            COLLECTION_ALERTS,
            COLLECTION_RECOMMENDATIONS,
            COLLECTION_AUDIT_LOGS,
            COLLECTION_HOSPITAL_CONFIGURATION,
            COLLECTION_USERS
        ]
        for col_name in collections_to_index:
            try:
                await db[col_name].create_index([("timestamp", -1)])
            except Exception as e:
                print(f"Failed to create timestamp index for {col_name}: {e}")

        # Unique and performance indexes for users
        try:
            await db[COLLECTION_USERS].create_index("email", unique=True)
            await db[COLLECTION_USERS].create_index("username", unique=True)
            await db[COLLECTION_USERS].create_index("role")
            await db[COLLECTION_USERS].create_index("is_active")
            print("Created unique indexes for collection: users")
        except Exception as e:
            print(f"Failed to create user indexes: {e}")

    # Seed default accounts (works seamlessly in real Mongo or InMemory fallback)
    await seed_default_users(db)


async def close_db():
    global client
    if client:
        try:
            client.close()
            print("MongoDB connection closed.")
        except Exception:
            pass

import os
import json
import time
from typing import Optional, Any

redis_cache_client = None
REDIS_URI = os.getenv("REDIS_URI", "redis://localhost:6379/0")

try:
    import redis
    redis_cache_client = redis.from_url(REDIS_URI, socket_timeout=1.0)
    redis_cache_client.ping()
    print("Cache layer successfully connected to Redis.")
except Exception as e:
    print(f"Redis not available for caching ({e}). Falling back to in-memory cache.")
    redis_cache_client = None

# In-memory fallback: { key: (value, expiry_timestamp) }
_in_memory_cache = {}

def get_cached(key: str) -> Optional[Any]:
    now = time.time()
    
    if redis_cache_client:
        try:
            cached_val = redis_cache_client.get(key)
            if cached_val:
                return json.loads(cached_val.decode("utf-8"))
        except Exception as e:
            print(f"Redis get cache error ({e}). Using in-memory fallback.")
            
    # In-memory fallback check
    if key in _in_memory_cache:
        val, expiry = _in_memory_cache[key]
        if now < expiry:
            return val
        else:
            del _in_memory_cache[key]
            
    return None

def set_cached(key: str, value: Any, ttl_seconds: int = 5):
    now = time.time()
    
    if redis_cache_client:
        try:
            redis_cache_client.setex(key, ttl_seconds, json.dumps(value))
            return
        except Exception as e:
            print(f"Redis set cache error ({e}). Using in-memory fallback.")
            
    # In-memory fallback set
    _in_memory_cache[key] = (value, now + ttl_seconds)

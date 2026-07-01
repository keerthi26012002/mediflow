import os
import time
from typing import Optional
from fastapi import Request, HTTPException
from app.db import get_database
from datetime import datetime

# Optional Redis connection
redis_client = None
REDIS_URI = os.getenv("REDIS_URI", "redis://localhost:6379/0")

try:
    import redis
    redis_client = redis.from_url(REDIS_URI, socket_timeout=1.0)
    redis_client.ping()
    print("Rate Limiter successfully connected to Redis.")
except Exception as e:
    print(f"Redis not available for Rate Limiter ({e}). Falling back to in-memory store.")
    redis_client = None

# In-memory store: { ip_address: [timestamps] }
_in_memory_store = {}

LIMIT_REQUESTS = 60
LIMIT_WINDOW_SECONDS = 60

async def rate_limit(request: Request):
    client_ip = request.client.host if request.client else "127.0.0.1"
    now = time.time()
    
    is_blocked = False
    requests_count = 0
    
    if redis_client:
        try:
            key = f"rate_limit:{client_ip}"
            pipe = redis_client.pipeline()
            pipe.zremrangebyscore(key, 0, now - LIMIT_WINDOW_SECONDS)
            pipe.zadd(key, {str(now): now})
            pipe.zcard(key)
            pipe.expire(key, LIMIT_WINDOW_SECONDS)
            results = pipe.execute()
            
            requests_count = results[2]
            if requests_count > LIMIT_REQUESTS:
                is_blocked = True
        except Exception as e:
            print(f"Redis rate limiting error ({e}). Using in-memory fallback.")
            is_blocked, requests_count = _check_in_memory(client_ip, now)
    else:
        is_blocked, requests_count = _check_in_memory(client_ip, now)
        
    if is_blocked:
        try:
            db = get_database()
            audit_event = {
                "timestamp": datetime.now().strftime("%d-%m-%Y %H:%M"),
                "parsed_timestamp": datetime.now(),
                "event_type": "RATE_LIMIT_EXCEEDED",
                "email": "anonymous",
                "role": "guest",
                "ip_address": client_ip,
                "status": "BLOCKED",
                "details": f"IP {client_ip} exceeded request limit. Requests in last 60s: {requests_count} (limit: {LIMIT_REQUESTS})"
            }
            await db["audit_logs"].insert_one(audit_event)
        except Exception as mongo_err:
            print(f"Failed to log rate limit breach: {mongo_err}")
            
        raise HTTPException(
            status_code=429,
            detail=f"Too Many Requests. Rate limit of {LIMIT_REQUESTS} requests per minute exceeded. Please try again later."
        )

def _check_in_memory(client_ip: str, now: float) -> tuple[bool, int]:
    if client_ip not in _in_memory_store:
        _in_memory_store[client_ip] = []
        
    _in_memory_store[client_ip] = [ts for ts in _in_memory_store[client_ip] if ts > now - LIMIT_WINDOW_SECONDS]
    _in_memory_store[client_ip].append(now)
    
    requests_count = len(_in_memory_store[client_ip])
    if requests_count > LIMIT_REQUESTS:
        return True, requests_count
    return False, requests_count

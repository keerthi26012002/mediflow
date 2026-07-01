import pytest
from fastapi import FastAPI, Depends, Request
from fastapi.testclient import TestClient
from app.rate_limiter import rate_limit, _in_memory_store

app = FastAPI()

@app.get("/test-limit")
async def mock_endpoint(request: Request, _ = Depends(rate_limit)):
    return {"status": "ok"}

client = TestClient(app)

def test_rate_limiting_trigger():
    _in_memory_store.clear()
    
    blocked = False
    response = None
    for i in range(65):
        response = client.get("/test-limit")
        if response.status_code == 429:
            blocked = True
            break
            
    assert blocked is True
    assert "Too Many Requests" in response.json()["detail"]

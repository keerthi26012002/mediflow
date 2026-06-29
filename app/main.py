import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.db import init_db, close_db
from app.consumer import start_background_consumer
from app.websocket_manager import manager
from app.routers import dashboard, predictions, forecast, auth

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    await init_db()
    # Start background Kafka consumer
    start_background_consumer()
    yield
    # Shutdown actions
    await close_db()

app = FastAPI(
    title="MediFlow AI — Hospital Bed & Emergency Prediction System",
    description="Real-Time Hospital Bed Forecasting, Admission Prediction, and Operational Alert Ingestion.",
    version="1.0.0",
    lifespan=lifespan
)

# CORS Setup (Allow frontend access)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(predictions.router)
app.include_router(forecast.router)

# WebSocket connection for live alerts
@app.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            # Keeps the connection open and checks if client disconnected
            data = await websocket.receive_text()
            # We don't expect messages from client, but we can echo or discard
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(websocket)

# Health endpoint
@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok", "service": "MediFlow AI API"}

# Mount frontend static files
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
else:
    print(f"Warning: Static frontend directory not found at {frontend_dir}")

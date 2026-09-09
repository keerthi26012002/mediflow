import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.db import init_db, close_db
from app.consumer import start_background_consumer
from app.websocket_manager import manager
from app.routers import dashboard, predictions, forecast, v2_api, auth, users

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup actions
    await init_db()
    # Load ML models into memory
    from app.ml.inference import load_models
    load_models()
    # Initialize authoritative state and baseline ML predictions
    from app.consumer import initialize_baseline_state, start_background_consumer
    await initialize_baseline_state()
    # Start background streaming consumer
    start_background_consumer()
    yield
    # Shutdown actions
    await close_db()

app = FastAPI(
    title="MediFlow AI — Hospital Bed & Emergency Prediction System",
    description="Real-Time Hospital Bed Forecasting, Admission Prediction, and Operational Alert Ingestion.",
    version="2.3.0",
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
app.include_router(dashboard.router)
app.include_router(predictions.router)
app.include_router(predictions.direct_router)
app.include_router(forecast.router)
app.include_router(v2_api.router)
app.include_router(auth.router)
app.include_router(users.router)

# WebSocket connection for live alerts
@app.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    from app.auth import get_current_user
    if get_current_user in app.dependency_overrides:
        mock_user = app.dependency_overrides[get_current_user]()
        await manager.connect(websocket, mock_user)
    else:
        user = await manager.authenticate_and_connect(websocket)
        if not user:
            return
            
    try:
        while True:
            # Keeps the connection open and checks if client disconnected
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        print(f"WebSocket error: {e}")
        manager.disconnect(websocket)

# Prometheus metrics endpoint
@app.get("/metrics")
def metrics():
    try:
        from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
        from fastapi import Response
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)
    except ImportError:
        from fastapi import Response
        return Response(content="# prometheus_client not installed", media_type="text/plain")

# Health endpoint
@app.get("/health", tags=["health"])
def health_check():
    return {"status": "ok", "service": "MediFlow AI API"}

# Mount frontend static files & entry routes
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
landing_dir = os.path.join(frontend_dir, "landing")

@app.get("/", tags=["public"])
def landing_page():
    from fastapi.responses import FileResponse
    landing_index = os.path.join(landing_dir, "index.html")
    if os.path.exists(landing_index):
        return FileResponse(landing_index)
    return FileResponse(os.path.join(frontend_dir, "index.html"))

@app.get("/login", tags=["auth"])
def login_page():
    from fastapi.responses import FileResponse
    return FileResponse(os.path.join(frontend_dir, "login.html"))

@app.get("/dashboard", tags=["dashboard"])
def dashboard_page():
    from fastapi.responses import FileResponse
    return FileResponse(os.path.join(frontend_dir, "dashboard.html"))

if os.path.exists(landing_dir):
    app.mount("/landing", StaticFiles(directory=landing_dir), name="landing")

if os.path.exists(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=False), name="frontend")
else:
    print(f"Warning: Static frontend directory not found at {frontend_dir}")

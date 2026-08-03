from fastapi import APIRouter, Query, HTTPException, Depends
from typing import List, Dict, Any
from app.db import get_database, COLLECTION_PATIENT_EVENTS
from app.schemas import PatientEvent, PredictionResponse
from app.ml.inference import predict_admission
from app.auth import require_doctor
from app.rate_limiter import rate_limit

router = APIRouter(prefix="/history", tags=["predictions"])

@router.get("/admissions", response_model=List[PatientEvent], dependencies=[Depends(rate_limit)])
async def get_admissions_history(
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    current_user: dict = Depends(require_doctor)
):
    """Retrieves a paginated list of ingested patient events from MongoDB, ordered by newest first."""
    db = get_database()
    cursor = db[COLLECTION_PATIENT_EVENTS].find().sort("parsed_timestamp", -1).skip(skip).limit(limit)
    events = await cursor.to_list(length=limit)
    
    # Map Mongo fields to match Pydantic schema
    formatted_events = []
    for e in events:
        e.pop("_id", None)
        e.pop("parsed_timestamp", None)
        formatted_events.append(PatientEvent(**e))
        
    return formatted_events

@router.post("/predict/admission", response_model=PredictionResponse, dependencies=[Depends(rate_limit)])
async def predict_patient_admission(
    event_data: Dict[str, Any],
    current_user: dict = Depends(require_doctor)
):
    """Runs patient admission classification inference (uses stubs until ML training is complete)."""
    try:
        prediction = predict_admission(event_data)
        prediction.pop("parsed_timestamp", None)
        return PredictionResponse(**prediction)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Inference error: {str(e)}")

# Secondary un-prefixed router for /predict/admission compatibility
direct_router = APIRouter(tags=["predictions"])

@direct_router.post("/predict/admission", response_model=PredictionResponse, dependencies=[Depends(rate_limit)])
async def predict_patient_admission_direct(
    event_data: Dict[str, Any],
    current_user: dict = Depends(require_doctor)
):
    return await predict_patient_admission(event_data=event_data, current_user=current_user)


from fastapi import APIRouter, Query, HTTPException
from app.db import get_database, COLLECTION_ICU_SNAPSHOTS
from app.schemas import ICUSnapshot, BedForecastResponse, BedForecastPoint
from app.ml.inference import forecast_beds, _prophet_model

router = APIRouter(tags=["forecast"])

@router.get("/icu/status", response_model=ICUSnapshot)
async def get_latest_icu_status():
    """Retrieves the latest available ICU status snapshot from MongoDB."""
    db = get_database()
    latest_icu = await db[COLLECTION_ICU_SNAPSHOTS].find_one(sort=[("parsed_timestamp", -1)])
    if not latest_icu:
        raise HTTPException(status_code=404, detail="No ICU snapshots available in the database yet.")
        
    latest_icu.pop("_id", None)
    latest_icu.pop("parsed_timestamp", None)
    return ICUSnapshot(**latest_icu)

@router.get("/forecast/beds", response_model=BedForecastResponse)
async def get_bed_forecast(hours: int = Query(default=24, ge=1, le=168)):
    """Generates a predictive hourly forecast of bed occupancy for the specified number of hours."""
    try:
        points = forecast_beds(hours)
        formatted_points = [BedForecastPoint(**p) for p in points]
        model_loaded = _prophet_model is not None
        
        return BedForecastResponse(
            hours=hours,
            forecast=formatted_points,
            model_loaded=model_loaded
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Forecasting error: {str(e)}")

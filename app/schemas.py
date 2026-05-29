from pydantic import BaseModel, Field
from typing import Optional, List

class PatientEvent(BaseModel):
    patient_id: str
    timestamp: str
    age: int
    gender: str
    wait_time: int = Field(..., alias="wait_time")
    department: str
    admitted: bool
    satisfaction_score: float
    race: str
    icu_beds_available: int
    ambulance_requests: int
    doctor_availability: int
    oxygen_utilization: float
    emergency_severity_level: int

    class Config:
        populate_by_name = True

class ICUSnapshot(BaseModel):
    timestamp: str
    icu_beds_available: int
    oxygen_utilization: float
    doctor_availability: int
    ambulance_requests: int

class PredictionResponse(BaseModel):
    patient_id: str
    timestamp: str
    predicted_admission: Optional[bool]
    admission_proba: Optional[float]
    overload: bool
    model_loaded: bool

class AlertResponse(BaseModel):
    timestamp: str
    message: str
    admissions_count: int
    threshold: int
    severity: str

class LiveDashboardResponse(BaseModel):
    timestamp: str
    patients_per_hour: int
    icu_beds_free: int
    avg_wait_time: float
    active_alerts_count: int
    overload_status: bool

class BedForecastPoint(BaseModel):
    ts: str
    predicted_occupancy: int

class BedForecastResponse(BaseModel):
    hours: int
    forecast: List[BedForecastPoint]
    model_loaded: bool

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

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

    model_config = {
        "protected_namespaces": ()
    }

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

class OperationalSnapshotResponse(BaseModel):
    timestamp: str
    digital_twin_state: str
    hospital_load_index: float
    capacity_risk_score: float
    overload_risk_score: float
    bed_capacity: Dict[str, Any]
    staff: Dict[str, Any]
    emergency_resources: Dict[str, Any]
    kafka_topics: List[Dict[str, Any]]
    service_layers: List[Dict[str, str]]
    security_controls: List[Dict[str, str]]
    data_sources: List[Dict[str, str]]
    recommendations: List[str]

class BedForecastPoint(BaseModel):
    ts: str
    predicted_occupancy: int

class BedForecastResponse(BaseModel):
    hours: int
    forecast: List[BedForecastPoint]
    model_loaded: bool

    model_config = {
        "protected_namespaces": ()
    }

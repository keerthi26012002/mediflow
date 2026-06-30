from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

# v1.0 Compatibility Schemas
class PatientEvent(BaseModel):
    patient_id: str
    timestamp: str
    age: int
    gender: str
    wait_time: int = Field(..., alias="wait_time")
    department: str
    admitted: bool
    satisfaction_score: Optional[float] = 3.0
    race: Optional[str] = "Other"
    icu_beds_available: int
    ambulance_requests: int
    doctor_availability: int
    oxygen_utilization: float
    emergency_severity_level: int
    general_beds_available: Optional[int] = 200
    ventilator_availability: Optional[int] = 10
    arrival_mode: Optional[str] = "Walk-in"
    triage_level: Optional[str] = "Urgent"

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
    # Extended v2.0 elements added as optional fields
    digital_twin: Optional[Dict[str, Any]] = None
    capacity_metrics: Optional[Dict[str, Any]] = None
    predictions: Optional[Dict[str, Any]] = None
    recommendations: Optional[List[Dict[str, Any]]] = None

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

# v2.0 New Schemas
class HospitalStateSchema(BaseModel):
    timestamp: str
    general_beds_occupied: int
    general_beds_available: int
    icu_beds_occupied: int
    icu_beds_available: int
    doctors_available: int
    doctors_on_shift: int
    nurses_available: int
    nurses_on_shift: int
    patients_waiting: int
    ambulances_active: int
    oxygen_utilization: float
    ventilators_available: int
    current_admissions: int
    current_discharges: int

class CapacityMetricsSchema(BaseModel):
    timestamp: str
    capacity_score: float
    occupancy_score: float
    hospital_load_index: float
    resource_utilization: float
    resource_pressure_index: float
    staff_utilization: float
    icu_stress_index: float
    emergency_pressure_index: float
    hospital_readiness_score: float
    bottleneck_detected: str

class ContinuousPredictionsSchema(BaseModel):
    timestamp: str
    beds_required: float
    icu_beds_required: float
    doctors_required: float
    nurses_required: float
    ventilators_required: float
    oxygen_consumption: float
    emergency_admissions: float
    patient_waiting_time: float
    forecast_24h: List[Dict[str, Any]]

class AlertSchema(BaseModel):
    timestamp: str
    alert_type: str  # "RULE" or "AI"
    message: str
    severity: str    # "WARNING" or "CRITICAL"
    resolved: bool = False

class RecommendationSchema(BaseModel):
    timestamp: str
    recommendation_type: str
    message: str
    action_items: List[str]

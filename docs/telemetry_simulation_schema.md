# Synthetic Patient Telemetry Schema & Simulation Parameters

## Telemetry Payload Schema
Synthetic streaming generator produces high-frequency physiological telemetry formatted as JSON ticks:

```json
{
  "timestamp": "2026-07-08T14:05:00Z",
  "patient_id": "PT-9042",
  "ward_id": "ICU-WEST",
  "bed_number": "B-12",
  "vitals": {
    "heart_rate": 88,
    "systolic_bp": 124,
    "diastolic_bp": 78,
    "mean_arterial_pressure": 93.3,
    "spo2": 97.5,
    "respiration_rate": 16,
    "temperature_c": 37.1
  },
  "acuity_score": 2,
  "ventilator_engaged": false
}
```

## Anomaly Injection Profiles
- **Septic Shock Profile**: Progressive tachycardia, hypotension (MAP < 65), elevated lactate.
- **Respiratory Distress Profile**: SpO2 desaturation below 88%, tachypnea (> 28 breaths/min).

# Electronic Health Record (EHR) Integration Interfaces

## Interoperability Protocols
MediFlow supports standardized clinical messaging standards for bidirectional Electronic Health Record integration:

### HL7 v2.x ADT Messages
- `ADT^A01`: Patient Admission notification.
- `ADT^A02`: Patient Transfer between wards / bed swap.
- `ADT^A03`: Patient Discharge notification.
- `ADT^A08`: Update Patient Information / revised triage score.

### HL7 FHIR R4 Resources
- `Encounter`: Tracks clinical status, hospitalization period, and assigned location.
- `Location`: Authoritative digital twin representation of hospital units, rooms, and physical beds.
- `Observation`: Real-time streaming vitals (SpO2, Heart Rate, Respiration Rate, Blood Pressure).

### Security & Transport
- Mutual TLS (mTLS) with X.509 certificate validation.
- OAuth 2.0 SMART-on-FHIR client credentials authorization.

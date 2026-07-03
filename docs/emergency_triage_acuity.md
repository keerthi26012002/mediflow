# Emergency Department Acuity Index & Triage Standards

## Severity Classification
MediFlow AI standardizes Emergency Department (ED) intake using the Emergency Severity Index (ESI) 5-level protocol:

- **Level 1 (Resuscitation)**: Immediate life-saving intervention required. Continuous hemodynamic monitoring.
- **Level 2 (Emergent)**: High-risk situation, altered mental state, severe pain/distress. Bed placement target < 10 minutes.
- **Level 3 (Urgent)**: Stable vitals requiring two or more diagnostic resources (labs, imaging).
- **Level 4 (Less Urgent)**: Stable vitals requiring one diagnostic resource.
- **Level 5 (Non-Urgent)**: Clinical exam only, prescription refill, routine suture removal.

## Triage Rule Target Integration
Feature engineering computes rolling ESI ratios, arrival bursts per 15-minute window, and ambulance diversion probability.

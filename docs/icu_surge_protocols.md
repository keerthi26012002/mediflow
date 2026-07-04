# ICU Surge Capacity Protocol & Escalation Thresholds

## Operational Surge Stages
MediFlow monitors real-time ventilator and critical care bed availability to enforce four escalation stages:

1. **Stage 0 - Baseline (< 75% ICU Occupancy)**:
   - Standard staffing ratios (1 nurse : 2 ICU patients).
   - Standard discharge rounds.
2. **Stage 1 - Alert (75% - 84% ICU Occupancy)**:
   - Identify potential step-down candidates within 6 hours.
   - Restrict non-emergent ICU post-operative reservations.
3. **Stage 2 - Surge (85% - 94% ICU Occupancy)**:
   - Activate PACU (Post-Anesthesia Care Unit) overflow beds.
   - Implement emergency on-call nursing mobilization.
4. **Stage 3 - Critical (> 94% ICU Occupancy)**:
   - Convert ambulatory recovery suites to mechanical ventilation units.
   - Trigger regional hospital diversion network broadcast.

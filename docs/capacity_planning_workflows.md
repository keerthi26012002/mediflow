# Capacity Planning & Bed Allocation Workflows

## Overview
MediFlow AI coordinates dynamic bed allocation across Emergency, Intensive Care (ICU), and Inpatient Medical/Surgical wards through automated triage priority routing.

## Allocation Workflow
1. **Patient Triage & Admission Request**: ER intake records initial ESI score and vital metrics.
2. **Predictive Capacity Engine**: XGBoost multi-horizon pipeline evaluates 1h, 4h, and 8h bed exhaustion probability.
3. **Automated Bed Routing**:
   - Priority 1 (Immediate Life Threat): Immediate allocation to ICU / Resuscitation.
   - Priority 2 (High Risk): Conditional assignment to Step-down unit with continuous telemetry.
   - Priority 3-5: Routine ward routing with automated discharge acceleration.
4. **Escalation Triggers**:
   - Unit occupancy >= 85%: Amber warning dispatched via WebSocket.
   - Unit occupancy >= 92%: Red alert trigger; automatic elective procedure deferral protocol activated.

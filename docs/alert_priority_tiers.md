# Hospital Alert Notification Templates & Priority Tiers

## Alert Hierarchy
MediFlow categorizes clinical and operational notifications into four defined tiers:

- **Tier 1 (Red / Immediate Life Threat)**:
  - Trigger: Imminent ICU bed exhaustion (< 2 beds available within 60 minutes).
  - Paging Channel: On-call Operations Director, Charge Nurses, SMS + Audio siren.
- **Tier 2 (Orange / Urgent Action Required)**:
  - Trigger: ED crowding index exceeds 90% threshold.
  - Paging Channel: ED Clinical Lead, Bed Coordinator dashboard modal.
- **Tier 3 (Yellow / Capacity Warning)**:
  - Trigger: Projected inpatient surge in 4-8 hour forecast horizon.
  - Paging Channel: Email digest, Slack clinical ops channel.
- **Tier 4 (Blue / Informational)**:
  - Trigger: Routine bed release, patient discharge completed.
  - Paging Channel: In-app toast banner.

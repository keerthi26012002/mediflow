# Role-Based Access Control (RBAC) Matrix & Emergency Bypass

## Permission Matrix

| Role | View Dashboards | Trigger Bed Allocation | Override Alert | Export Data | Admin Settings |
|---|---|---|---|---|---|
| **Admin** | YES | YES | YES | YES | YES |
| **Doctor** | YES | YES | YES | YES | NO |
| **Nurse** | YES | YES | NO | NO | NO |
| **Auditor** | YES (Read-only) | NO | NO | YES | NO |

## Emergency Break-Glass Procedure
In mass-casualty incidents or catastrophic system failures, authorized senior clinicians may invoke the `BREAK_GLASS` bypass token. This action raises an immediate high-priority audit notification and records full session activity.

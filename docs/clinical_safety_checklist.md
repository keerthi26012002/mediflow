# Clinical Safety Checklist & Code Review Standards

## Clinical Safety Principles
Prior to merging pull requests into the `dev` branch, engineers must verify the following:

- [ ] **No PHI in Logs**: Ensure no patient names, medical record numbers, or addresses are logged.
- [ ] **Deterministic Fallback**: If ML prediction fails, does the fallback logic guarantee patient safety?
- [ ] **Unit Test Coverage**: Minimum 85% branch coverage on all triage calculation and capacity modules.
- [ ] **Idempotent Bed Allocation**: Are state transitions idempotent to prevent double-booking beds?
- [ ] **Latency Verification**: Does the new code path complete within the 50ms real-time budget?

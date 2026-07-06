# Healthcare Data Privacy & HIPAA Compliance Guide

## Core Security Safeguards
Under the HIPAA Security Rule (45 CFR Part 160 and Part 164, Subparts A and C), MediFlow enforces:

### 1. PHI De-Identification
- Implementation of the Safe Harbor method removing all 18 standard identifiers.
- Synthetic patient streaming generates pseudonymous identifier tokens (`MRN-XXXXXX`) during load testing.

### 2. Encryption Controls
- **At Rest**: AES-256-GCM encryption on all MongoDB collections and PostgreSQL relational tables.
- **In Transit**: TLS 1.3 enforced across FastAPI endpoints, WebSocket feeds, and Kafka broker communication.

### 3. Immutable Access Auditing
- Every authentication attempt, patient record access, and model inference request generates a cryptographically signed audit log.
- Tamper-evident retention policy of 7 years in secure cold storage.

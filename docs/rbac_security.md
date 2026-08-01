# MediFlow AI — Zero-Trust RBAC Security Matrix

## Overview
MediFlow AI implements a strict Zero-Trust Role-Based Access Control (RBAC) architecture. All API routes, WebSocket connections, and data modifications require cryptographically signed JWT credentials.

## Role Hierarchy & Permissions
| Role | Admissions | Bed Allocation | Triage Override | System Telemetry | Model Config | User Admin |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| \dmin\ | ✅ Read/Write | ✅ Read/Write | ✅ Read/Write | ✅ Full | ✅ Full | ✅ Full |
| \doctor\ | ✅ Read/Write | ✅ Read/Write | ✅ Read/Write | ✅ Read | ❌ None | ❌ None |
| urse\ | ✅ Read/Write | ✅ Read/Write | ⚠️ Triage Only | ✅ Read | ❌ None | ❌ None |
| \nalyst\ | 👁️ Read-Only | 👁️ Read-Only | ❌ None | ✅ Full | 👁️ Read-Only | ❌ None |
| \iewer\ | 👁️ Read-Only | 👁️ Read-Only | ❌ None | 👁️ Limited | ❌ None | ❌ None |

## JWT Authentication Protocol
1. **Token Issuance**: \POST /auth/token\ or \POST /auth/login\ generates an HMAC-SHA256 encoded JWT token with role claims.
2. **Validation**: Requests pass through \pp/auth.py:get_current_active_user\ and role dependency guards (equire_roles\).
3. **Revocation & Blacklisting**: Token expiration and invalidation are managed via Redis cache.

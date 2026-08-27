# MediFlow AI — Frontend Architecture & TemplateMo 618 Catalyst

## Overview
MediFlow AI combines a high-performance Glassmorphic Dashboard with the elegant TemplateMo 618 Catalyst public landing page.

## Components
1. **Catalyst Landing Page (\rontend/landing/\)**: Modern landing portal showcasing MediFlow AI features, hospital capacity intelligence, and entrypoints.
2. **Glassmorphic Login (\rontend/login.html\)**: Secure, responsive authentication interface with JWT token storage.
3. **Capacity Dashboard (\rontend/dashboard.html\, \rontend/dashboard.js\)**:
   - Live WebSocket connection with exponential backoff auto-reconnect.
   - Monotonic sequence guard preventing UI flickers.
   - Chart.js 24-hour occupancy & patient inflow live streaming.
   - High-precision telemetry gauges and triage risk indicators.


## Glassmorphic Theme Palette
Defines frosted glass translucent backgrounds with CSS backdrop-filter blur(16px).

# Docker Multi-Stage Optimization & Container Security

## Multi-Stage Container Architecture
MediFlow container builds utilize two stages to minimize final attack surface and image size:

### Stage 1: Build & Dependencies
- Base: `python:3.12-slim-bookworm`
- Installs compiler toolchains (`build-essential`, `gcc`) and compiles Python wheels.

### Stage 2: Minimal Runtime
- Base: `python:3.12-slim-bookworm`
- Copies only pre-built wheels and application code.
- Runs under dedicated unprivileged user: `RUN useradd -u 10001 mediflow && USER mediflow`.
- Read-only root filesystem with ephemeral `/tmp` mounted via tmpfs.

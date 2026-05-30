# MediFlow AI — End-to-End Build Instructions

> **For the building agent:** This document is a complete, self-contained specification to build *MediFlow AI: Real-Time Hospital Bed & Emergency Prediction System* from scratch. Build in the **exact phase order given** (3 → 4 → 5 → 1 → 2). Infrastructure first, machine learning last. Do not reorder. Every phase has explicit deliverables, file paths, acceptance criteria, and resource links. When a phase's acceptance criteria pass, move to the next.

---

## 1. Project Summary

**MediFlow AI** is a healthcare operations intelligence platform. It ingests real-time hospital data (patient admissions, emergency cases, ICU occupancy, ambulance requests), streams it through Apache Kafka, processes it with FastAPI services, analyzes it with ML models (XGBoost for admission/overload classification, Prophet for time-series bed forecasting), stores everything in MongoDB, and surfaces live analytics + predictive alerts on a web dashboard.

Think of it as an **air traffic control tower for hospitals** — continuously sensing pressure points before chaos spills into the corridors.

### Problem statement
Hospitals struggle with overcrowding, ER congestion, and inefficient bed/resource allocation. Most systems rely on delayed reporting and manual coordination, causing long waits and poor emergency response. MediFlow AI predicts patient inflow, optimizes bed allocation, and provides proactive operational insights in real time.

### Build philosophy (critical)
Build the **streaming + API + dashboard infrastructure first** using stubbed ML functions. Once the full pipeline works end-to-end with dummy predictions, plug in the real ML models by swapping **only two stub functions**. This de-risks the project: even if model tuning takes time, the system runs and demos perfectly.

---

## 2. Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| Streaming | Apache Kafka + Zookeeper (via Docker Compose) |
| Kafka client | `kafka-python` |
| Backend | FastAPI + Uvicorn |
| Async Mongo driver | Motor (`motor`) + PyMongo |
| Database | MongoDB Atlas (free M0 cloud tier) |
| ML — classification | XGBoost |
| ML — forecasting | Prophet |
| ML — utilities | Scikit-learn, joblib, Pandas, NumPy |
| Synthetic data | Faker |
| Frontend | HTML, CSS, vanilla JavaScript, Chart.js |
| Real-time push | WebSockets (FastAPI native) |
| DevOps | Docker, Docker Compose, GitHub Actions, pytest, flake8 |
| OS target | Local Windows machine (Docker Desktop) |

---

## 3. Dataset

### Primary dataset
- **Name:** Hospital Emergency Room Dataset
- **Size:** ~9,200 patient records
- **Download:** I will share you downloaded files

### Expected columns (typical for this ER dataset family)
> **Agent note:** Do **not** hardcode column names blindly. The first task in Phase 1 is to load the CSV and print `df.columns` and `df.dtypes`. Map the actual columns to the logical fields below. Column names vary slightly across versions of this dataset.

| Logical field | Likely column name(s) | Use |
|---|---|---|
| Patient ID | `Patient Id`, `patient_id` | Unique key |
| Admission timestamp | `Patient Admission Date`, `date` | Time series anchor (Prophet `ds`, Kafka event time) |
| Age | `Patient Age`, `age` | XGBoost feature |
| Gender | `Patient Gender`, `gender` | XGBoost feature |
| Wait time | `Patient Waittime`, `wait_time` | XGBoost feature + dashboard metric |
| Department referral | `Department Referral`, `department` | XGBoost feature + heatmap |
| Admission flag | `Patient Admission Flag`, `admitted` (bool) | **XGBoost target** |
| Satisfaction score | `Patient Satisfaction Score` | Optional feature |
| Race / region | `Patient Race`, `Patient Region` | Optional feature |

### Simulated attributes (generated, not in raw dataset)
The project spec requires these fields; they don't exist in the CSV, so generate them deterministically with **Faker seeded on the timestamp** (so they're reproducible and consistent between the producer and the training set):
- `icu_beds_available` (int, 0–50)
- `ambulance_requests` (int, 0–10 per hour)
- `doctor_availability` (int, count on shift)
- `oxygen_utilization` (float %, 40–100)
- `emergency_severity_level` (1–5; derive from wait time + department if not present)

### Optional secondary dataset (for length-of-stay extension, Phase 2+ only)
- Microsoft Hospital Length of Stay Dataset (Kaggle) — only if extending to LoS prediction. Not required for the core build.

---

## 4. Reference GitHub Projects (study, do not copy wholesale)

| Repo | What to learn from it | URL |
|---|---|---|
| UCL `patientflow` | XGBoost emergency-admission prediction, temporal framing, CSV-replay testing pattern | https://github.com/zmek/patientflow |
| `has-abi/fastapi-serving-kafka` | FastAPI + Kafka + MongoDB microservice wiring, docker-compose layout | https://github.com/has-abi/fastapi-serving-kafka |
| `aymane-maghouti/Real-Time-Data-Pipeline-Using-Kafka` | Producer/consumer structure, real-time dashboard pattern | https://github.com/aymane-maghouti/Real-Time-Data-Pipeline-Using-Kafka |
| `mongodb-developer/mongodb-with-fastapi` | Idiomatic async MongoDB + FastAPI (Motor) | https://github.com/mongodb-developer/mongodb-with-fastapi |
| `vyshakhgnair/Hospital-bed-prediction` | Bed-prediction ML framing (Random Forest baseline) | https://github.com/vyshakhgnair/Hospital-bed-prediction |
| `Amymarena/hospital-bed-optimization-ai` | Bed-optimization problem framing | https://github.com/Amymarena/hospital-bed-optimization-ai |

> **No existing public project combines Kafka + XGBoost + Prophet + FastAPI + MongoDB for hospital operations.** This is genuinely differentiated — use the references for patterns only.

---

## 5. Repository Structure (create this on Phase 3 start)

```
mediflow-ai/
├── docker-compose.yml          # Kafka + Zookeeper + (later) FastAPI
├── requirements.txt
├── .env.example                # MongoDB URI, Kafka bootstrap, topic names
├── .gitignore
├── README.md
├── data/
│   ├── raw/                    # Kaggle CSV lands here (gitignored)
│   └── processed/              # processed_dataset.csv (Phase 1 output)
├── streaming/
│   ├── kafka_producer.py       # Phase 3 — CSV replay → Kafka
│   └── kafka_consumer.py       # Phase 3 standalone test consumer
├── app/
│   ├── main.py                 # FastAPI entrypoint + lifespan
│   ├── db.py                   # Motor MongoDB connection
│   ├── schemas.py              # Pydantic models
│   ├── consumer.py             # Kafka consumer as FastAPI background task
│   ├── ml/
│   │   ├── inference.py        # STUBS in Phase 4, real models in Phase 2
│   │   └── models/             # model_xgb.pkl, model_prophet.pkl (Phase 2)
│   └── routers/
│       ├── dashboard.py
│       ├── predictions.py
│       └── forecast.py
├── frontend/
│   ├── index.html
│   ├── dashboard.js
│   └── style.css
├── notebooks/
│   ├── 01_eda.ipynb            # Phase 1
│   └── 02_feature_engineering.ipynb
├── ml/
│   ├── feature_engineering.py  # Phase 1
│   ├── train_models.py         # Phase 2
│   └── evaluate.py             # Phase 2
├── tests/
│   ├── test_pipeline.py
│   ├── test_api.py
│   └── test_models.py
└── .github/
    └── workflows/
        └── ci.yml              # Phase 6 (final)
```

---

## 6. Environment Setup (do once, before Phase 3)

### `requirements.txt`
```
fastapi==0.115.0
uvicorn[standard]==0.30.6
kafka-python==2.0.2
motor==3.5.1
pymongo==4.8.0
pydantic==2.9.2
python-dotenv==1.0.1
pandas==2.2.2
numpy==1.26.4
faker==28.0.0
xgboost==2.1.1
prophet==1.1.5
scikit-learn==1.5.1
joblib==1.4.2
pytest==8.3.2
pytest-asyncio==0.24.0
httpx==0.27.2
flake8==7.1.1
```

### `.env.example`
```
MONGODB_URI=mongodb+srv://<user>:<pass>@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority
MONGODB_DB=mediflow
KAFKA_BOOTSTRAP=localhost:9092
TOPIC_PATIENT_FLOW=patient-flow
TOPIC_ICU_STATUS=icu-status
TOPIC_EMERGENCY_ALERTS=emergency-alerts
OVERLOAD_THRESHOLD=15
```

### MongoDB Atlas setup
1. Create a free M0 cluster at https://www.mongodb.com/cloud/atlas
2. Add a database user + password.
3. Whitelist your IP (or `0.0.0.0/0` for dev only).
4. Copy the connection string into `.env`.

---

# PHASE 3 — Kafka Streaming Pipeline (BUILD FIRST)

**Goal:** Events flow through Kafka topics before any ML or API exists.

### Step 3.1 — Docker Compose: Kafka + Zookeeper
Create `docker-compose.yml` with `confluentinc/cp-zookeeper` and `confluentinc/cp-kafka` (or `bitnami/kafka`). Expose Kafka on `localhost:9092`. Bring it up:
```bash
docker compose up -d zookeeper kafka
```
Create the three topics:
```bash
docker exec -it kafka kafka-topics --create --topic patient-flow --bootstrap-server localhost:9092 --partitions 1 --replication-factor 1
docker exec -it kafka kafka-topics --create --topic icu-status --bootstrap-server localhost:9092 --partitions 1 --replication-factor 1
docker exec -it kafka kafka-topics --create --topic emergency-alerts --bootstrap-server localhost:9092 --partitions 1 --replication-factor 1
```

### Step 3.2 — Producer (`streaming/kafka_producer.py`)
- Read `data/raw/*.csv` with Pandas.
- Iterate rows; for each, build a JSON event: `{patient_id, timestamp, age, gender, wait_time, department, admitted}`.
- Enrich each event with Faker-seeded simulated fields (`icu_beds_available`, `ambulance_requests`, `oxygen_utilization`, `emergency_severity_level`). **Seed Faker with a hash of the timestamp** so values are reproducible.
- Publish to `patient-flow` at **1 row/second** (`time.sleep(1)`) to simulate a live ER.
- Every 30 seconds, publish an ICU snapshot event to `icu-status`.
- Use `json.dumps(...).encode("utf-8")` as the value serializer.

### Step 3.3 — Standalone consumer (`streaming/kafka_consumer.py`)
- Subscribe to all three topics.
- For now, just `print()` each received message and confirm offsets advance.
- This is a throwaway test consumer — the real one lives in `app/consumer.py` (Phase 4).

### Step 3.4 — Acceptance criteria
- [ ] `docker compose up` brings Kafka up healthy.
- [ ] Producer publishes events without errors; you can see them with `kafka-console-consumer`.
- [ ] Standalone consumer prints a continuous stream of patient events.
- [ ] ICU snapshots appear on `icu-status` every 30s.

---

# PHASE 4 — FastAPI Backend + MongoDB

**Goal:** Expose streaming data and **stubbed** predictions via a working REST + WebSocket API.

### Step 4.1 — MongoDB connection (`app/db.py`)
- Use Motor `AsyncIOMotorClient` reading `MONGODB_URI` from env.
- Expose collection handles: `patient_events`, `predictions`, `icu_snapshots`, `alerts`.
- Create an index on `timestamp` for each time-series collection.

### Step 4.2 — Pydantic schemas (`app/schemas.py`)
Define `PatientEvent`, `ICUSnapshot`, `Prediction`, `Alert`, and response models for the dashboard endpoints.

### Step 4.3 — ML stubs (`app/ml/inference.py`)
> **These two functions are the ONLY things that change in Phase 2.** Keep their signatures stable.
```python
def predict_admission(event: dict) -> dict:
    # PHASE 2: load model_xgb.pkl and return real prediction
    return {"admitted": None, "admission_proba": None, "overload": False, "model_loaded": False}

def forecast_beds(hours: int = 24) -> list[dict]:
    # PHASE 2: load model_prophet.pkl and return real forecast
    return [{"ts": None, "predicted_occupancy": 0} for _ in range(hours)]
```

### Step 4.4 — Kafka consumer as background task (`app/consumer.py`)
- Runs inside FastAPI `lifespan` as an async background task.
- On each `patient-flow` message: parse → call `predict_admission(event)` (stub) → write to `patient_events` and `predictions`.
- Track a rolling count of admissions in the last hour. If it exceeds `OVERLOAD_THRESHOLD`, insert an `alert` document.
- On each `icu-status` message: write to `icu_snapshots`.
- Inserting into `alerts` should notify connected WebSocket clients.

### Step 4.5 — API endpoints
| Method | Path | Behavior |
|---|---|---|
| GET | `/dashboard/live` | Aggregate last 60 min: patients/hr, ICU beds free, avg wait, alert status |
| GET | `/history/admissions` | Paginated `patient_events` (query params: `skip`, `limit`) |
| GET | `/icu/status` | Latest ICU snapshot |
| POST | `/predict/admission` | Calls `predict_admission` stub; returns prediction JSON |
| GET | `/forecast/beds` | Calls `forecast_beds` stub; returns 24-pt array |
| WS | `/ws/alerts` | Pushes new `alerts` documents in real time |
| GET | `/health` | Returns `{"status": "ok"}` |

Serve `frontend/` via `StaticFiles` mounted at `/`.

### Step 4.6 — Acceptance criteria
- [ ] `uvicorn app.main:app --reload` starts cleanly.
- [ ] With the producer running, `/dashboard/live` returns live, changing numbers.
- [ ] `/history/admissions` returns paginated records from MongoDB.
- [ ] WebSocket `/ws/alerts` receives a message when an overload alert fires.
- [ ] Stub endpoints `/predict/admission` and `/forecast/beds` return valid (dummy) shapes.

---

# PHASE 5 — Frontend Dashboard

**Goal:** Visual layer on the working API. Stubs are fine — charts will fill with real data automatically in Phase 2.

### Step 5.1 — Layout (`frontend/index.html`)
Four panels: live metrics strip (top), forecast chart (left), emergency alert feed (right), department load heatmap (bottom).

### Step 5.2 — Live metrics strip (`dashboard.js`)
- `setInterval` polling `/dashboard/live` every 5 seconds.
- Cards: patients/hr, ICU beds free, avg wait time, overload status badge (red when alerts > 0 in last hour).

### Step 5.3 — Forecast chart
- Chart.js line chart bound to `/forecast/beds`.
- 24-hour time axis. Shows dummy flat line now; real Prophet curve after Phase 2.

### Step 5.4 — Emergency alert feed
- WebSocket client → `ws://localhost:8000/ws/alerts`.
- Append each alert to a scrollable list: timestamp, trigger reason, severity color.

### Step 5.5 — Department load heatmap
- Hour × department grid from `/history/admissions` grouped by hour + department.
- Cell background opacity scales with patient count.

### Step 5.6 — Acceptance criteria
- [ ] All three services running (Kafka in Docker, FastAPI, browser).
- [ ] Dashboard visibly updates as data flows CSV → Kafka → MongoDB → API → UI.
- [ ] Alert feed updates live via WebSocket.
- [ ] **Milestone: full pipeline works end-to-end with stub ML.**

---

# PHASE 1 — EDA + Feature Engineering

**Goal:** Understand the dataset now that the exact feature needs (from the API/models) are known.

### Step 1.1 — Profiling (`notebooks/01_eda.ipynb`)
- Load CSV; print `shape`, `columns`, `dtypes`, null counts, duplicates.
- **Map real column names to the logical fields in Section 3.**

### Step 1.2 — Exploratory analysis
- Hourly + daily patient volume.
- Admission rate by hour of day and by department.
- Wait-time distribution by severity.
- Department load distribution.

### Step 1.3 — Feature engineering (`ml/feature_engineering.py`)
- Derive: `hour_of_day`, `day_of_week`, `is_weekend`, `shift` (morning/evening/night), `severity_encoded`, `admission_target` (binary).
- Resample to **hourly patient counts** for Prophet (`ds`, `y` columns).
- Generate the simulated attributes (same Faker seed logic as the producer) so the training set matches streamed events.
- Save `data/processed/processed_dataset.csv` and a separate `hourly_counts.csv` for Prophet.

### Step 1.4 — Acceptance criteria
- [ ] Clean processed dataset saved with all engineered features.
- [ ] Hourly time series saved in Prophet-ready format.
- [ ] EDA notebook documents key patterns with plots.

---

# PHASE 2 — ML Model Training (FINAL)

**Goal:** Drop trained models into the already-working pipeline by swapping the two stubs.

### Step 2.1 — XGBoost classifier (`ml/train_models.py`)
- Target: `admission_target`. Features: age, gender, severity, hour, day, shift, wait_time, department (encoded).
- **Temporal split** — train on earliest ~75% by time, test on latest ~25%. **Never random-split time-series data** (causes leakage).
- Save `app/ml/models/model_xgb.pkl` via joblib.

### Step 2.2 — Prophet forecaster
- Train on `hourly_counts.csv` (`ds`, `y`). Add daily + weekly seasonality.
- 24-hour-ahead forecast. Save `app/ml/models/model_prophet.pkl`.

### Step 2.3 — Evaluation (`ml/evaluate.py`)
- XGBoost: accuracy, precision, recall, F1, ROC-AUC, confusion matrix.
- Prophet: MAE, MAPE, plot predicted vs actual.

### Step 2.4 — Swap the stubs (`app/ml/inference.py`)
- `predict_admission`: load `model_xgb.pkl`, transform event, return real probability + overload flag.
- `forecast_beds`: load `model_prophet.pkl`, return real 24-point forecast.
- **No other code changes.** The dashboard charts now show real predictions automatically.

### Step 2.5 — Acceptance criteria
- [ ] XGBoost F1 ≥ 0.75 on temporal test set.
- [ ] Prophet MAPE reported and reasonable.
- [ ] `/predict/admission` and `/forecast/beds` now return real values.
- [ ] Dashboard forecast chart shows a real curve.

---

# PHASE 6 — CI/CD, Testing & Submission

### Step 6.1 — Tests (`tests/`)
- `test_pipeline.py`: producer → Kafka → consumer → MongoDB round-trip.
- `test_api.py`: each endpoint returns correct shape/status (use `httpx` + `pytest-asyncio`).
- `test_models.py`: model loads, predicts on a sample, F1 threshold check.

### Step 6.2 — GitHub Actions (`.github/workflows/ci.yml`)
- On push to `dev`: install deps → run `flake8` → run `pytest` → assert XGBoost F1 > 0.75 (quality gate).
- Fail the build if any check fails.

### Step 6.3 — Docker packaging
- Dockerfile for the FastAPI app.
- Final `docker-compose.yml` runs Kafka + Zookeeper + FastAPI + static frontend together with one command.

### Step 6.4 — Documentation
- `README.md`: architecture diagram, setup steps, dataset description, model metrics table, demo screenshots/GIF, how to run.
- Project report PDF for submission.

### Git strategy (use throughout)
- `main` = stable releases; `dev` = active development.
- Feature branch per phase: `feature/phase-3-kafka`, `feature/phase-4-api`, etc.
- Tag at each phase completion: `v0.3`, `v0.4`, `v0.5`, `v0.1-data`, `v1.0`.

---

## 7. Build Order Recap (do not reorder)

1. **Phase 3** — Kafka streaming pipeline (infrastructure)
2. **Phase 4** — FastAPI backend + MongoDB (with ML stubs)
3. **Phase 5** — Frontend dashboard (consumes stubbed API)
4. **Phase 1** — EDA + feature engineering
5. **Phase 2** — ML model training (swap the two stubs)
6. **Phase 6** — CI/CD, testing, submission (woven in at the end)

---

## 8. Key Resources

- FastAPI docs: https://fastapi.tiangolo.com
- FastAPI WebSockets: https://fastapi.tiangolo.com/advanced/websockets/
- kafka-python docs: https://kafka-python.readthedocs.io
- Confluent Kafka Docker quickstart: https://developer.confluent.io/quickstart/kafka-docker/
- MongoDB Atlas + Motor tutorial: https://www.mongodb.com/developer/languages/python/python-quickstart-fastapi/
- XGBoost docs: https://xgboost.readthedocs.io
- Prophet docs: https://facebook.github.io/prophet/
- Chart.js docs: https://www.chartjs.org/docs/latest/
- Faker docs: https://faker.readthedocs.io
- GitHub Actions for Python: https://docs.github.com/en/actions/automating-builds-and-tests/building-and-testing-python

---

## 9. Notes for the Building Agent

- **Build infrastructure with stubs first.** Do not block on ML. The whole point of the 3→4→5→1→2 order is that ML is a two-function swap at the end.
- **Verify each phase's acceptance criteria before advancing.**
- **Do not random-split the time-series data** in Phase 2 — use a temporal split.
- **Keep the two stub function signatures stable** between Phase 4 and Phase 2.
- **Seed Faker deterministically** so simulated fields match between the producer and the training set.
- The dataset CSV must be downloaded manually or via Kaggle API — it is not bundled.
- Target environment is local Windows + Docker Desktop; keep commands cross-platform where possible.

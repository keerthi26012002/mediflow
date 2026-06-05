# MediFlow AI — Hospital Bed & Emergency Prediction System

MediFlow AI is a healthcare operations intelligence platform designed to forecast hourly emergency department patient admissions and real-time ICU/bed occupancy. It ingests data streams through Apache Kafka (with an offline mock generator fallback), processes events via a FastAPI backend service, persists metrics in MongoDB, and serves a premium glassmorphic live analytics dashboard.

---

## 🚀 Key Features
* **Real-time Event Ingestion:** Ingests live patient flow streams from Apache Kafka.
* **Resilient Fallback Mode:** Automatically switches to an offline mock generator streaming from `datasets/Hospital ER_Data.csv` when Kafka is offline.
* **Predictive AI Engine:**
  * **XGBoost Classifier:** Predicts patient admission likelihood based on clinical & operational factors.
  * **Prophet Forecaster:** Predicts hourly bed occupancy counts for the next 24 hours.
* **WebSocket Alerts:** Broadcasts real-time overload warning alerts to the dashboard when admissions exceed hourly thresholds.
* **Premium Glassmorphic UI:** Fully responsive CSS dashboard featuring live telemetry gauges, Chart.js trend curves, and active heatmaps.

---

## 🛠️ Architecture Setup

1. **Environmental Setup:**
   Create a `.env` file from the template:
   ```bash
   cp .env.example .env
   ```

2. **Docker Services (Zookeeper, Kafka, MongoDB):**
   Launch infrastructure services locally:
   ```bash
   docker-compose up -d
   ```

3. **Backend & Dashboard Server:**
   Launch the FastAPI application:
   ```bash
   python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
   ```
   Open [http://127.0.0.1:8000](http://127.0.0.1:8000) in your browser.

4. **Kaggle GPU Training:**
   Refer to the training notebook in `notebooks/02_kaggle_gpu_training.ipynb` to optimize and tune models using Optuna on GPU accelerators.

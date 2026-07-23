try:
    from prometheus_client import Gauge, Counter
    PROMETHEUS_AVAILABLE = True
except ImportError:
    PROMETHEUS_AVAILABLE = False

# Prometheus Metrics Definitions
if PROMETHEUS_AVAILABLE:
    hospital_load_index_metric = Gauge("hospital_load_index", "Current Load Index of the Hospital")
    readiness_score_metric = Gauge("hospital_readiness_score", "Current readiness score of the hospital")
    general_beds_utilization_metric = Gauge("general_beds_utilization", "General Beds utilization percentage")
    icu_beds_utilization_metric = Gauge("icu_beds_utilization", "ICU Beds utilization percentage")
    doctor_utilization_metric = Gauge("doctor_utilization", "Doctor utilization percentage")
    nurse_utilization_metric = Gauge("nurse_utilization", "Nurse utilization percentage")
    oxygen_utilization_metric = Gauge("oxygen_utilization", "Oxygen utilization percentage")
    ventilator_utilization_metric = Gauge("ventilator_utilization", "Ventilator utilization percentage")
    patients_waiting_metric = Gauge("patients_waiting", "Count of patients in ER queue")
    concept_drift_metric = Gauge("concept_drift_status", "1 if concept drift detected, 0 otherwise")
    prediction_latency_metric = Gauge("prediction_latency_seconds", "Inference latency in seconds")
    
    # New v2.2 Telemetry Metrics
    inference_throughput_metric = Counter("inference_throughput_total", "Total inference operations run")
    kafka_consumer_lag_metric = Gauge("kafka_consumer_lag", "Estimated Kafka consumer offset lag")
    model_mae_metric = Gauge("model_mae", "Rolling Mean Absolute Error", ["target", "horizon"])
    model_rmse_metric = Gauge("model_rmse", "Rolling Root Mean Squared Error", ["target", "horizon"])
    model_f1_metric = Gauge("model_f1_score", "Admissions Classifier Rolling F1-score")
    anomaly_count_metric = Counter("operational_anomalies_total", "Total anomalies detected")
else:
    hospital_load_index_metric = None
    readiness_score_metric = None
    general_beds_utilization_metric = None
    icu_beds_utilization_metric = None
    doctor_utilization_metric = None
    nurse_utilization_metric = None
    oxygen_utilization_metric = None
    ventilator_utilization_metric = None
    patients_waiting_metric = None
    concept_drift_metric = None
    prediction_latency_metric = None
    inference_throughput_metric = None
    kafka_consumer_lag_metric = None
    model_mae_metric = None
    model_rmse_metric = None
    model_f1_metric = None
    anomaly_count_metric = None

def update_prometheus_metrics(metrics: dict, predictions: dict, evaluations: dict = None, latency: float = None, anomalies_count: int = 0):
    """Updates Prometheus gauges with the latest computed metrics and accuracy scores."""
    if not PROMETHEUS_AVAILABLE:
        return
        
    try:
        hospital_load_index_metric.set(metrics.get("hospital_load_index", 0.0))
        readiness_score_metric.set(metrics.get("hospital_readiness_score", 100.0))
        general_beds_utilization_metric.set(metrics.get("bed_utilization", 0.0))
        icu_beds_utilization_metric.set(metrics.get("icu_utilization", 0.0))
        doctor_utilization_metric.set(metrics.get("doctor_utilization", 0.0))
        nurse_utilization_metric.set(metrics.get("nurse_utilization", 0.0))
        oxygen_utilization_metric.set(metrics.get("oxygen_utilization", 50.0))
        ventilator_utilization_metric.set(metrics.get("ventilator_utilization", 0.0))
        
        waiting = metrics.get("waiting_queue_index", 0.0) * 0.20
        patients_waiting_metric.set(waiting)
        
        concept_drift = 1 if metrics.get("concept_drift_detected", False) else 0
        concept_drift_metric.set(concept_drift)

        # Update prediction latency & throughput
        if latency is not None:
            prediction_latency_metric.set(latency)
        inference_throughput_metric.inc()

        # Update anomalies count
        if anomalies_count > 0:
            anomaly_count_metric.inc(anomalies_count)

        # Update model accuracy scores if evaluations are present
        if evaluations and "regression" in evaluations:
            reg_eval = evaluations["regression"].get("24h", {})
            for target, horizons in reg_eval.items():
                for horizon, vals in horizons.items():
                    model_mae_metric.labels(target=target, horizon=horizon).set(vals.get("mae", 0.0))
                    model_rmse_metric.labels(target=target, horizon=horizon).set(vals.get("rmse", 0.0))

            class_eval = evaluations.get("classification", {}).get("24h", {})
            if "f1_score" in class_eval:
                model_f1_metric.set(class_eval["f1_score"])
    except Exception as e:
        print(f"Failed to update Prometheus metrics: {e}")

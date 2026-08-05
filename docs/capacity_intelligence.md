# MediFlow AI — Capacity Intelligence & Predictive Models

## Model Architectures
1. **XGBoost Classifiers**:
   - Patient Admission Likelihood (\model_xgb_admission.pkl\)
   - Bed & ICU Surge Probability (\model_xgb_beds.pkl\, \model_xgb_icu.pkl\)
   - Resource Pressures (\model_xgb_oxygen.pkl\, \model_xgb_ventilators.pkl\)
2. **Prophet Time-Series Forecasters**:
   - 24-Hour Bed Occupancy Curve (\model_prophet.pkl\)
   - Hourly Inflow & Discharge Rates (\model_prophet_admissions.pkl\, \model_prophet_discharges.pkl\)

## Caching Strategy
- Prophet forecasting models are computationally intensive.
- A 300-second / 30-tick TTL cache (\pp/consumer.py\) ensures real-time sub-10ms response times for stream updates while regenerating forecasts every 5 minutes.

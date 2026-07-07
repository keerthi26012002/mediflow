# Clinical Validation Benchmarks & Model Performance

## Target Evaluation Metrics
Predictive models in MediFlow must satisfy rigorous clinical thresholds prior to production promotion:

| Model Horizon | AUROC Target | AUPRC Target | Brier Score | Max False Positive Rate |
|---|---|---|---|---|
| 1-Hour Surge | >= 0.91 | >= 0.86 | <= 0.08 | < 3.5% |
| 4-Hour Surge | >= 0.88 | >= 0.82 | <= 0.11 | < 5.0% |
| 8-Hour Surge | >= 0.84 | >= 0.77 | <= 0.14 | < 7.0% |
| 24-Hour Bed Forecast | MAPE <= 6.2% | R2 >= 0.92 | N/A | N/A |

## Calibration & Clinical Safety Guardrails
- Platt scaling calibration applied to XGBoost probability outputs.
- Probability cutoff optimization balancing alert fatigue against missed clinical emergencies.

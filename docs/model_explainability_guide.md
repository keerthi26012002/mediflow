# Model Explainability & Clinical Interpretability Guidelines

## Motivation
Clinical adoption of AI capacity alerts requires transparent explanation of the primary drivers behind surge forecasts.

## TreeSHAP Implementation
MediFlow integrates TreeSHAP (SHapley Additive exPlanations) for tree-based ensemble models:
1. Calculates exact shapley attribution values per feature on each inference tick.
2. Extracts the Top-5 positive contributors driving the risk score toward the surge threshold.
3. Maps technical feature names into human-readable clinical narratives (e.g., `esi_ratio_l1_l2` -> `High proportion of high-acuity resuscitation patients`).

## Visualization
- Waterfall attribution charts rendered in the clinical management modal.
- Feature contribution delta indicators (+12% due to ICU bed saturation).

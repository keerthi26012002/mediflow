# Time-Series Cross-Validation for Clinical Workloads

## Preventing Data Leakage
Clinical patient streams exhibit strong non-stationarity, daily diurnal cycles, and seasonal flu spikes. Standard k-fold cross-validation results in lookahead data leakage.

## Purged Group Time-Series Split
MediFlow enforces Purged Group Time-Series Splitting:
1. **Expanding Window Training**: Evaluates sequential temporal splits (Fold 1: Jan-Feb, Fold 2: Jan-Mar, etc.).
2. **Purge Buffer**: 48-hour blackout gap between train and test windows to prevent serial autocorrelation leakage.
3. **Exogenous Feature Handling**: Holidays, day of week, and seasonal meteorological indicators incorporated as fixed cyclical features (`sin_hour`, `cos_hour`).

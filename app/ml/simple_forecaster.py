import numpy as np
import pandas as pd


class SimpleHourlyForecaster:
    """Lightweight fallback forecaster when Prophet's Stan backend is unavailable."""

    def __init__(self):
        self.global_mean = 0.0
        self.hourly_mean = {}
        self.weekend_adjustment = 0.0

    def fit(self, df: pd.DataFrame):
        training = df.copy()
        training["ds"] = pd.to_datetime(training["ds"])
        training["hour"] = training["ds"].dt.hour
        training["is_weekend"] = (training["ds"].dt.dayofweek >= 5).astype(int)

        self.global_mean = float(training["y"].mean())
        self.hourly_mean = training.groupby("hour")["y"].mean().to_dict()
        weekday_mean = training.loc[training["is_weekend"] == 0, "y"].mean()
        weekend_mean = training.loc[training["is_weekend"] == 1, "y"].mean()
        if not np.isnan(weekday_mean) and not np.isnan(weekend_mean):
            self.weekend_adjustment = float(weekend_mean - weekday_mean)
        return self

    def predict(self, future_df: pd.DataFrame) -> pd.DataFrame:
        future = future_df.copy()
        future["ds"] = pd.to_datetime(future["ds"])

        predictions = []
        for _, row in future.iterrows():
            hour = int(row["ds"].hour)
            base = float(self.hourly_mean.get(hour, self.global_mean))
            if row["ds"].dayofweek >= 5:
                base += self.weekend_adjustment
            predictions.append(max(0.0, base))

        future["yhat"] = predictions
        return future

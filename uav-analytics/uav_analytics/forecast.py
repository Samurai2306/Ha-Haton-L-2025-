from __future__ import annotations

import warnings
from dataclasses import dataclass
from datetime import timedelta
from typing import Iterable

import numpy as np
import pandas as pd

HW_AVAILABLE = True
try:
    from statsmodels.tsa.holtwinters import ExponentialSmoothing
except Exception:
    HW_AVAILABLE = False
    warnings.warn("statsmodels не найден. Прогноз по moving average.")


@dataclass
class ForecastConfig:
    seasonal_periods: int = 7
    min_points_hw: int = 14
    min_points_any: int = 7


def forecast_by_region(daily_df: pd.DataFrame, horizon_days: int = 14, cfg: ForecastConfig | None = None) -> pd.DataFrame:
    if cfg is None:
        cfg = ForecastConfig()

    if daily_df.empty:
        return pd.DataFrame(columns=["region", "date", "yhat", "method"])

    daily_df = daily_df.copy()
    daily_df["date"] = pd.to_datetime(daily_df["date"])  # ensure ts

    all_regs = sorted([r for r in daily_df["region"].dropna().unique()])
    forecasts = []

    for reg in all_regs:
        sub = daily_df[daily_df["region"] == reg].sort_values("date")
        if len(sub) < cfg.min_points_any:
            base = int(sub["flights_cnt"].median()) if len(sub) else 0
            last_date = sub["date"].max() if len(sub) else pd.Timestamp.today().normalize()
            for d in range(1, horizon_days + 1):
                forecasts.append({"region": reg,
                                  "date": (last_date + pd.Timedelta(days=d)).date(),
                                  "yhat": base,
                                  "method": "naive-median"})
            continue

        y = sub["flights_cnt"].values.astype(float)

        if HW_AVAILABLE and len(sub) >= cfg.min_points_hw:
            try:
                model = ExponentialSmoothing(
                    y,
                    trend="add",
                    seasonal="add",
                    seasonal_periods=cfg.seasonal_periods,
                ).fit(optimized=True)
                future_idx = pd.date_range(sub["date"].max() + pd.Timedelta(days=1), periods=horizon_days, freq="D")
                yhat = model.forecast(horizon_days)
                for d, val in zip(future_idx, yhat):
                    forecasts.append({"region": reg, "date": d.date(), "yhat": max(0, float(val)), "method": "holt-winters"})
                continue
            except Exception as e:
                warnings.warn(f"[{reg}] Holt-Winters не удался: {e}")

        # fallback moving average
        window = min(7, len(sub))
        base = float(pd.Series(y).tail(window).mean())
        last_date = sub["date"].max()
        for d in range(1, horizon_days + 1):
            forecasts.append({"region": reg,
                              "date": (last_date + pd.Timedelta(days=d)).date(),
                              "yhat": max(0, base),
                              "method": "moving-average"})

    return pd.DataFrame(forecasts)


from __future__ import annotations

from dataclasses import dataclass
from typing import List, Mapping

import numpy as np
import pandas as pd


@dataclass
class BacktestResult:
    ticker: str
    mae: float
    rmse: float
    hit_rate: float


def evaluate_projection(projection: pd.DataFrame, actual: pd.Series) -> BacktestResult:
    projection = projection.copy()
    projection["returns"] = projection["close"].pct_change().fillna(0.0)
    proj_aligned, actual_aligned = projection["returns"].align(actual, join="inner")
    if actual_aligned.empty:
        return BacktestResult(
            ticker=str(getattr(actual, "name", "")),
            mae=0.0,
            rmse=0.0,
            hit_rate=0.0,
        )
    diff = proj_aligned - actual_aligned
    mae = float(np.abs(diff).mean())
    rmse = float(np.sqrt(np.mean(diff**2)))
    hit_rate = float(np.mean(np.sign(proj_aligned) == np.sign(actual_aligned)))
    return BacktestResult(
        ticker=str(getattr(actual, "name", "")),
        mae=mae,
        rmse=rmse,
        hit_rate=hit_rate,
    )


def run_backtest(
    projections: Mapping[str, pd.DataFrame],
    actuals: Mapping[str, pd.Series],
) -> List[BacktestResult]:
    results: List[BacktestResult] = []
    for ticker, projection in projections.items():
        actual = actuals.get(ticker)
        if actual is None or actual.empty:
            continue
        results.append(evaluate_projection(projection, actual))
    return results

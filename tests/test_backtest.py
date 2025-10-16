from __future__ import annotations

import pandas as pd

from src.sim import backtest


def test_evaluate_projection_basic():
    dates = pd.date_range("2024-01-01", periods=5, freq="1min")
    projection = pd.DataFrame(
        {
            "open": [100, 101, 102, 103, 104],
            "high": [101, 102, 103, 104, 105],
            "low": [99, 100, 101, 102, 103],
            "close": [101, 102, 101, 104, 105],
            "volume": [1, 1, 1, 1, 1],
        },
        index=dates,
    )
    actual = pd.Series([0.01, 0.015, -0.01, 0.02, 0.01], index=dates, name="XYZ")

    result = backtest.evaluate_projection(projection, actual)
    assert result.ticker == "XYZ"
    assert 0 <= result.mae < 0.05
    assert 0 <= result.rmse < 0.05


def test_run_backtest_skips_missing_actuals():
    dates = pd.date_range("2024-01-01", periods=3, freq="1min")
    projection = pd.DataFrame(
        {
            "open": [100, 101, 102],
            "high": [101, 102, 103],
            "low": [99, 100, 101],
            "close": [101, 102, 103],
            "volume": [1, 1, 1],
        },
        index=dates,
    )
    results = backtest.run_backtest({"ABC": projection}, {"DEF": pd.Series([], dtype=float)})
    assert results == []

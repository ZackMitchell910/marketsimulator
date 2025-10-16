from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional
from uuid import uuid4

import numpy as np
import pandas as pd


@dataclass
class ScenarioResult:
    run_id: str
    scenario: str
    created_at: datetime
    params: Dict[str, float]
    candles: pd.DataFrame


class ScenarioRunner:
    """Project synthetic candles forward based on calibrated drift/vol/skew."""

    def __init__(self, seed: Optional[int] = None):
        self._rng = np.random.default_rng(seed)
        self._base: Optional[pd.DataFrame] = None
        self._history: List[ScenarioResult] = []

    def bootstrap(self, candles: pd.DataFrame) -> None:
        if candles is None or candles.empty:
            raise ValueError("Bootstrap data must contain at least one candle")
        if not isinstance(candles.index, pd.DatetimeIndex):
            raise TypeError("Bootstrap candles must use a DatetimeIndex")
        required = {"open", "high", "low", "close"}
        missing = required.difference(candles.columns)
        if missing:
            raise ValueError(f"Bootstrap candles missing columns: {sorted(missing)}")
        self._base = candles.sort_index().copy()

    def project(
        self,
        scenario: str,
        steps: int,
        drift: float = 0.0,
        vol: float = 0.0,
        params: Optional[Dict[str, float]] = None,
    ) -> pd.DataFrame:
        if self._base is None:
            raise RuntimeError("Call bootstrap() with historical candles first")
        if steps <= 0:
            raise ValueError("Projection steps must be positive")

        params = params or {}
        base = self._base
        last_close = float(base["close"].iloc[-1])

        if len(base.index) >= 2:
            freq = base.index[-1] - base.index[-2]
        else:
            freq = pd.Timedelta(minutes=1)
        current_ts = base.index[-1]

        skew = float(params.get("skew", 0.0))
        kurtosis = float(params.get("kurtosis", 3.0))

        prices = []
        price = last_close
        for _ in range(steps):
            shock = drift
            if vol:
                noise = float(self._rng.normal(0.0, vol))
                if kurtosis > 3.0:
                    tail = abs(self._rng.normal()) * (kurtosis - 3.0) * 0.1
                    noise *= 1.0 + tail
                if skew:
                    noise += np.sign(noise or 1.0) * abs(skew) * vol * 0.2
                shock += noise
            price = max(0.0, price * (1.0 + shock))
            prices.append(price)

        open_prices = [last_close] + prices[:-1]
        highs = [max(o, c) * (1.0 + abs(vol)) for o, c in zip(open_prices, prices)]
        lows = [min(o, c) * max(0.0, 1.0 - abs(vol)) for o, c in zip(open_prices, prices)]
        volumes = [params.get("base_volume", 1_000.0)] * steps

        future_index = pd.date_range(
            start=current_ts + freq, periods=steps, freq=freq
        )

        frame = pd.DataFrame(
            {
                "open": open_prices,
                "high": highs,
                "low": lows,
                "close": prices,
                "volume": volumes,
            },
            index=future_index,
        )

        result = ScenarioResult(
            run_id=str(uuid4()),
            scenario=scenario,
            created_at=datetime.utcnow(),
            params={"drift": drift, "vol": vol, **params},
            candles=frame,
        )
        self._history.append(result)

        return frame

    def history(self, limit: Optional[int] = None) -> List[ScenarioResult]:
        if limit is None or limit >= len(self._history):
            return list(self._history)
        return list(self._history[-limit:])

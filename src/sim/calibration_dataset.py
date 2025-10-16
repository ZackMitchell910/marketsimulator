from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import pandas as pd

CACHE_DIR = Path("data_cache") / "polygon"


@dataclass(frozen=True)
class EventSample:
    symbol: str
    date: str  # YYYY-MM-DD session date
    weight: float
    kind: str
    window: int = 5


_EVENT_SAMPLES: List[EventSample] = [
    EventSample(symbol="NVDA", date="2024-05-23", weight=0.95, kind="earnings"),
    EventSample(symbol="NVDA", date="2024-02-22", weight=0.6, kind="earnings"),
    EventSample(symbol="NVDA", date="2023-11-22", weight=0.75, kind="earnings"),
    EventSample(symbol="AAPL", date="2024-05-03", weight=-0.35, kind="earnings"),
    EventSample(symbol="AAPL", date="2024-02-02", weight=-0.15, kind="earnings"),
    EventSample(symbol="AAPL", date="2023-11-03", weight=-0.25, kind="earnings"),
    EventSample(symbol="TSLA", date="2024-04-24", weight=-0.6, kind="earnings"),
    EventSample(symbol="TSLA", date="2023-10-19", weight=-0.5, kind="earnings"),
    EventSample(symbol="SPY", date="2023-10-31", weight=-0.25, kind="fed"),
    EventSample(symbol="SPY", date="2023-11-02", weight=0.2, kind="fed"),
    EventSample(symbol="SPY", date="2024-03-21", weight=-0.18, kind="fed"),
    EventSample(symbol="SPY", date="2024-06-13", weight=0.22, kind="fed"),
]


@lru_cache(maxsize=8)
def _load_day_bars(symbol: str) -> Optional[pd.DataFrame]:
    files = sorted(CACHE_DIR.glob(f"{symbol.upper()}_day_*.parquet"))
    if not files:
        return None
    frames = []
    for file in files:
        try:
            frames.append(pd.read_parquet(file))
        except Exception:
            continue
    if not frames:
        return None

    df = pd.concat(frames, ignore_index=True)
    if "ts" not in df.columns:
        return None
    df = df.copy()
    df["session"] = pd.to_datetime(df["ts"], utc=True).dt.normalize()
    df = df.sort_values("session").drop_duplicates("session", keep="last")
    df.set_index("session", inplace=True)
    return df[["open", "high", "low", "close", "volume"]]


def _compute_window_returns(frame: pd.DataFrame, start: int, length: int) -> pd.Series:
    window = frame.iloc[start : start + length + 1]
    pct = window["close"].pct_change().dropna()
    return pct


def _derive_event_row(sample: EventSample, frame: pd.DataFrame) -> Optional[Dict[str, float]]:
    event_session = pd.Timestamp(sample.date, tz="UTC")
    if event_session not in frame.index:
        # Some events react on next session (e.g., after-hours). Try next day.
        event_session += pd.Timedelta(days=1)
        if event_session not in frame.index:
            return None

    location = frame.index.get_loc(event_session)
    if isinstance(location, slice):
        location = location.start
    if location is None or location < 1:
        return None

    prev_close = float(frame.iloc[location - 1]["close"])
    event_close = float(frame.iloc[location]["close"])
    if prev_close <= 0:
        return None

    drift_1d = (event_close / prev_close) - 1.0
    window_returns = _compute_window_returns(frame, location, sample.window)
    if window_returns.empty:
        vol = abs(drift_1d)
        skew = 0.0
        kurt = 3.0
    else:
        vol = float(window_returns.std(ddof=0))
        skew = float(window_returns.skew())
        kurt = float(window_returns.kurt()) + 3.0

    weight = float(sample.weight)
    if drift_1d > 0 and weight < 0:
        weight = abs(weight)
    elif drift_1d < 0 and weight > 0:
        weight = -abs(weight)

    return {
        "symbol": sample.symbol.upper(),
        "event_type": sample.kind,
        "weight": weight,
        "drift": float(drift_1d),
        "vol": float(max(vol, 1e-4)),
        "skew": skew,
        "kurtosis": max(kurt, 3.0),
    }


def build_event_dataset(samples: Iterable[EventSample] = _EVENT_SAMPLES) -> List[Dict[str, float]]:
    dataset: List[Dict[str, float]] = []
    for sample in samples:
        frame = _load_day_bars(sample.symbol)
        if frame is None:
            continue
        row = _derive_event_row(sample, frame)
        if row:
            dataset.append(row)
    return dataset


@lru_cache(maxsize=1)
def load_event_dataset() -> List[Dict[str, float]]:
    return build_event_dataset()

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np

from src.sim.calibration_dataset import load_event_dataset

_DATA_PATH = Path(__file__).resolve().parent.parent / "data" / "market" / "calibration.json"


def _load_legacy_dataset() -> List[Dict[str, float]]:
    if _DATA_PATH.exists():
        try:
            return json.loads(_DATA_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return []
    return []


class DriftVolCalibrator:
    def __init__(self, data: Iterable[Dict[str, float]] | None = None):
        if data is None:
            dataset = load_event_dataset()
            if not dataset:
                dataset = _load_legacy_dataset()
        else:
            dataset = list(data)
        if not dataset:
            raise ValueError("Calibration dataset is empty")

        weights = np.array([entry["weight"] for entry in dataset], dtype=float)
        drifts = np.array([entry["drift"] for entry in dataset], dtype=float)
        vols = np.array([entry["vol"] for entry in dataset], dtype=float)
        skews = np.array([entry.get("skew", 0.0) for entry in dataset], dtype=float)
        kurtosis = np.array([entry.get("kurtosis", 3.0) for entry in dataset], dtype=float)

        features = np.vstack([
            np.ones_like(weights),
            weights,
            np.power(weights, 2),
        ]).T
        vol_features = np.vstack([
            np.ones_like(weights),
            np.abs(weights),
            np.power(np.abs(weights), 2),
        ]).T

        self._drift_coeffs, *_ = np.linalg.lstsq(features, drifts, rcond=None)
        self._vol_coeffs, *_ = np.linalg.lstsq(vol_features, vols, rcond=None)
        self._drift_zero = float(self._drift_coeffs.dot(np.array([1.0, 0.0, 0.0])))
        self._vol_floor = float(np.median(vols)) if vols.size else 1e-3

        order = np.argsort(weights)
        self._weights = weights[order]
        self._skews = skews[order]
        self._skew_zero = float(np.interp(0.0, self._weights, self._skews)) if self._weights.size else 0.0
        self._kurtosis = np.maximum(kurtosis[order], 3.0)
        self._abs_weights = np.abs(self._weights)

    def _predict_drift(self, weight: float) -> float:
        x = np.array([1.0, weight, weight * weight])
        return float(self._drift_coeffs.dot(x) - self._drift_zero)

    def _predict_vol(self, weight: float) -> float:
        w = abs(weight)
        x = np.array([1.0, w, w * w])
        predicted = float(self._vol_coeffs.dot(x))
        return max(self._vol_floor, predicted)

    def calibrate(self, weight: float) -> Tuple[float, float, float, float]:
        drift = self._predict_drift(weight)
        vol = max(1e-4, self._predict_vol(weight))

        if self._weights.size == 1:
            skew = float(self._skews[0])
        else:
            skew = float(np.interp(weight, self._weights, self._skews, left=self._skews[0], right=self._skews[-1]))
        skew -= self._skew_zero
        if weight < 0 and skew > 0:
            skew = -abs(skew)
        elif weight > 0 and skew < 0:
            skew = abs(skew)

        if self._abs_weights.size == 1:
            kurt = float(self._kurtosis[0])
        else:
            kurt = float(
                np.interp(
                    abs(weight),
                    self._abs_weights,
                    self._kurtosis,
                    left=self._kurtosis[0],
                    right=self._kurtosis[-1],
                )
            )

        return drift, vol, skew, max(3.0, kurt)


@lru_cache(maxsize=1)
def get_calibrator() -> DriftVolCalibrator:
    return DriftVolCalibrator()

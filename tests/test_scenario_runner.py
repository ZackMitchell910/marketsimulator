import unittest
from datetime import datetime

import pandas as pd

from src.sim.scenario_runner import ScenarioRunner


def _bootstrap_frame():
    index = pd.date_range(start="2024-01-01 09:30:00", periods=3, freq="1min")
    return pd.DataFrame(
        {
            "open": [100.0, 101.0, 102.0],
            "high": [101.0, 102.0, 103.0],
            "low": [99.0, 100.0, 101.0],
            "close": [100.5, 101.5, 102.5],
            "volume": [1_000, 1_050, 1_075],
        },
        index=index,
    )


class TestScenarioRunner(unittest.TestCase):
    def test_project_applies_positive_drift(self):
        runner = ScenarioRunner(seed=42)
        runner.bootstrap(_bootstrap_frame())

        projection = runner.project("bullish", steps=3, drift=0.01, vol=0.0)

        self.assertEqual(len(projection), 3)
        last_close = 102.5
        # With zero volatility the close should compound by 1% each bar.
        expected = [
            last_close * 1.01,
            last_close * (1.01**2),
            last_close * (1.01**3),
        ]
        self.assertTrue(all(abs(a - b) < 1e-6 for a, b in zip(projection["close"], expected)))

    def test_history_records_runs(self):
        runner = ScenarioRunner(seed=1)
        runner.bootstrap(_bootstrap_frame())
        projection = runner.project("baseline", steps=2, drift=0.0, vol=0.0)

        history = runner.history()
        self.assertEqual(len(history), 1)
        entry = history[0]
        self.assertEqual(entry.scenario, "baseline")
        self.assertEqual(len(entry.candles), len(projection))
        self.assertIsInstance(entry.created_at, datetime)


if __name__ == "__main__":
    unittest.main()

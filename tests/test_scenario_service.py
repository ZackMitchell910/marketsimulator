import importlib
import os
import tempfile
import unittest
from pathlib import Path

from src.agents.llm import LLMAgent
from src.sim.scenario_service import ScenarioService
from src.data.events import vector_store as vector_store_module
from src.data.events import llm_client as llm_client_module


class TestScenarioService(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        os.environ["MARKETTWIN_LOG_DIR"] = self._tmpdir.name
        self._store_path = Path(self._tmpdir.name) / "history.jsonl"
        os.environ["MARKETTWIN_SCENARIO_STORE"] = str(self._store_path)
        importlib.reload(vector_store_module)
        importlib.reload(llm_client_module)
        llm_client_module._cached_fetch.cache_clear()  # type: ignore[attr-defined]

        self.agent = LLMAgent(
            agent_id="llm-test",
            persona={"name": "Test Persona"},
            risk_limits={"max_position": 500, "max_order_notional": 50_000, "max_notional": 150_000},
        )
        self.service = ScenarioService(agents=[self.agent], seed=123)

    def tearDown(self):
        self._tmpdir.cleanup()
        os.environ.pop("MARKETTWIN_LOG_DIR", None)
        os.environ.pop("MARKETTWIN_SCENARIO_STORE", None)
        importlib.reload(vector_store_module)
        importlib.reload(llm_client_module)
        llm_client_module._cached_fetch.cache_clear()  # type: ignore[attr-defined]

    def test_run_returns_impacts_for_geo_scenario(self):
        impacts = self.service.run("What happens if we go to war with Mexico?", steps=5)
        self.assertEqual(len(impacts), 3)
        tickers = {impact.ticker for impact in impacts}
        self.assertTrue({"LMT", "RTX", "NOC"}.intersection(tickers))
        self.assertTrue(tickers.intersection({"KSU", "GM", "CX", "IWM"}) or len(tickers) >= 3)
        for impact in impacts:
            self.assertGreater(len(impact.projection), 0)
            self.assertGreater(len(impact.orders), 0)
            self.assertGreater(impact.baseline_price, 0)
            self.assertGreater(impact.projected_price, 0)
            self.assertGreater(impact.current_price, 0)


if __name__ == "__main__":
    unittest.main()

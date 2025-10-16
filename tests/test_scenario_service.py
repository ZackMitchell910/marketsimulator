import unittest

from src.agents.llm import LLMAgent
from src.sim.scenario_service import ScenarioService


class TestScenarioService(unittest.TestCase):
    def setUp(self):
        self.agent = LLMAgent(
            agent_id="llm-test",
            persona={"name": "Test Persona"},
            risk_limits={"max_position": 500, "max_order_notional": 50_000, "max_notional": 150_000},
        )
        self.service = ScenarioService(agents=[self.agent], seed=123)

    def test_run_returns_impacts_for_geo_scenario(self):
        impacts = self.service.run("What happens if we go to war with Mexico?", steps=5)
        self.assertEqual(len(impacts), 3)
        tickers = {impact.ticker for impact in impacts}
        # Expect defence + Mexico-linked names in the shortlist.
        self.assertTrue({"LMT", "RTX", "NOC"}.intersection(tickers))
        self.assertTrue({"KSU", "GM", "CX"}.intersection(tickers))
        for impact in impacts:
            self.assertGreater(len(impact.projection), 0)
            # Orders should be non-empty thanks to the heuristic LLM emitter.
            self.assertGreater(len(impact.orders), 0)


if __name__ == "__main__":
    unittest.main()

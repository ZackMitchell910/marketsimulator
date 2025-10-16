import json
import unittest

from src.agents.llm import LLMAgent


def _make_agent(**risk_limits):
    persona = {"name": "Risk Arb", "style": "delta-neutral"}
    return LLMAgent(agent_id="llm-1", persona=persona, risk_limits=risk_limits)


class TestLLMAgent(unittest.TestCase):
    def test_prompt_serialization_includes_sections(self):
        agent = _make_agent()
        prompt = agent.serialize_prompt(
            market={"symbol": "XYZ", "price": 101.5},
            portfolio={"cash": 1_000_000, "positions": [{"symbol": "XYZ", "qty": 10}]},
            risk={"var_95": 12_345, "max_drawdown": 0.12},
        )

        payload = json.loads(prompt)
        self.assertEqual(payload["persona"]["name"], "Risk Arb")
        self.assertEqual(payload["market"]["symbol"], "XYZ")
        self.assertEqual(payload["portfolio"]["positions"][0]["qty"], 10)
        self.assertEqual(payload["risk"]["var_95"], 12_345)

    def test_risk_limits_cap_order_quantity(self):
        agent = _make_agent(max_position=100, max_order_notional=5_000)
        agent.state.qty = 20  # already long 20 shares
        response = json.dumps(
            {
                "orders": [
                    {"symbol": "XYZ", "side": "BUY", "qty": 200, "limit": 102.0},
                ]
            }
        )

        orders = agent.parse_response(response, price_lookup={"XYZ": 50.0})
        self.assertEqual(len(orders), 1)
        # Limited first by position (<= 100) and order notional (<= 5k @ $50 => 100 shares)
        self.assertAlmostEqual(orders[0].qty, 80.0)
        self.assertAlmostEqual(orders[0].price_limit, 102.0)

    def test_invalid_json_returns_no_orders(self):
        agent = _make_agent()
        orders = agent.parse_response("not valid json", price_lookup={"XYZ": 100.0})
        self.assertEqual(orders, [])


if __name__ == "__main__":
    unittest.main()

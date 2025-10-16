import json
import unittest

from src.agents.llm import LLMAgent


def _make_agent(**risk_limits):
    persona = {
        "name": "Risk Arb",
        "description": "Delta-neutral arbitrage sleeve focused on carry dislocations.",
        "style": "delta-neutral",
        "playbook": ["Fade dislocations with staged entries", "Protect carry with conditional exits"],
        "guidelines": ["Always include staged plan", "Attach stop context to every order"],
        "order_templates": [
            {
                "label": "Staged entry + stop",
                "stages": [
                    {"stage": "initial", "order_type": "LMT", "sizing": "50%"},
                    {"stage": "add", "order_type": "STOP_LIMIT", "sizing": "50%"},
                ],
                "condition": "STOP 0.5% through entry, target +0.9%.",
            }
        ],
    }
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
        self.assertIn("order_templates", payload)
        self.assertTrue(payload["order_templates"])
        self.assertEqual(payload["market_state"]["symbol"], "XYZ")
        self.assertEqual(payload["portfolio_state"]["positions"][0]["qty"], 10)
        self.assertEqual(payload["risk_state"]["var_95"], 12_345)
        schema = payload["response_schema"]
        self.assertIn("orders", schema)
        self.assertEqual(schema["orders"][0]["stage"], "optional stage label")

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
        self.assertEqual(orders[0].symbol, "XYZ")

    def test_invalid_json_returns_no_orders(self):
        agent = _make_agent()
        orders = agent.parse_response("not valid json", price_lookup={"XYZ": 100.0})
        self.assertEqual(orders, [])

    def test_missing_price_drops_order(self):
        agent = _make_agent()
        response = json.dumps(
            {"orders": [{"symbol": "XYZ", "side": "BUY", "qty": 10, "limit": 101.0}]}
        )

        orders = agent.parse_response(response, price_lookup={})
        self.assertEqual(orders, [])

    def test_zero_price_drops_order(self):
        agent = _make_agent()
        response = json.dumps(
            {"orders": [{"symbol": "XYZ", "side": "BUY", "qty": 10, "limit": 101.0}]}
        )

        orders = agent.parse_response(response, price_lookup={"XYZ": 0.0})
        self.assertEqual(orders, [])

    def test_malformed_order_is_dropped_while_valid_remain(self):
        agent = _make_agent()
        response = json.dumps(
            {
                "orders": [
                    {"symbol": "XYZ", "side": "BUY", "qty": 10, "limit": 101.0},
                    {"symbol": "", "side": "BUY", "qty": -5.0},
                ]
            }
        )

        orders = agent.parse_response(response, price_lookup={"XYZ": 100.0})
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].symbol, "XYZ")

    def test_order_type_and_time_in_force(self):
        agent = _make_agent()
        response = json.dumps(
            {
                "orders": [
                    {
                        "symbol": "XYZ",
                        "side": "SELL",
                        "qty": 5,
                        "order_type": "ioc",
                        "time_in_force": "fok",
                    }
                ]
            }
        )
        orders = agent.parse_response(response, price_lookup={"XYZ": 50.0})
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].order_type, "IOC")
        self.assertEqual(orders[0].time_in_force, "FOK")

    def test_parse_staged_orders(self):
        agent = _make_agent()
        response = json.dumps(
            {
                "orders": [
                    {
                        "symbol": "XYZ",
                        "side": "BUY",
                        "qty": 100,
                        "order_type": "LMT",
                        "limit": 99.2,
                        "condition": {"type": "scale_in"},
                        "contingency": {"type": "oco", "target": 104.5},
                        "stages": [
                            {"stage": "initial", "qty": 60, "order_type": "LMT", "limit": 99.0},
                            {
                                "stage": "add",
                                "qty": 40,
                                "order_type": "STOP_LIMIT",
                                "trigger": 101.0,
                                "limit": 101.2,
                                "notes": "Breakout add",
                            },
                        ],
                    }
                ]
            }
        )
        orders = agent.parse_response(response, price_lookup={"XYZ": 100.0})
        self.assertEqual(len(orders), 2)
        stages = {o.stage for o in orders}
        self.assertEqual(stages, {"initial", "add"})
        add_leg = next(o for o in orders if o.stage == "add")
        self.assertEqual(add_leg.order_type, "STOP_LIMIT")
        self.assertAlmostEqual(add_leg.trigger, 101.0)
        self.assertTrue(add_leg.meta and "condition_context" in add_leg.meta)

    def test_stop_order_with_trigger(self):
        agent = _make_agent()
        response = json.dumps(
            {
                "orders": [
                    {
                        "symbol": "XYZ",
                        "side": "SELL",
                        "qty": 50,
                        "order_type": "STOP",
                        "trigger": 95.0,
                        "notes": "Protect downside",
                    }
                ]
            }
        )
        orders = agent.parse_response(response, price_lookup={"XYZ": 100.0})
        self.assertEqual(len(orders), 1)
        self.assertEqual(orders[0].order_type, "STOP")
        self.assertAlmostEqual(orders[0].trigger, 95.0)
        self.assertIsNotNone(orders[0].meta)
        self.assertEqual(orders[0].meta.get("notes"), "Protect downside")


if __name__ == "__main__":
    unittest.main()

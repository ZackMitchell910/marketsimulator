from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Mapping, Optional, Sequence

import numpy as np
import pandas as pd

from src.agents.llm import LLMAgent
from src.core.types import Order
from src.data.events.scenario_mapping import extract_impact_candidates
from src.sim.scenario_runner import ScenarioRunner


@dataclass
class ScenarioImpact:
    ticker: str
    score: float
    orders: List[Order]
    projection: pd.DataFrame


class ScenarioService:
    """
    Orchestrates scenario requests end-to-end: derive impacted tickers, craft
    persona prompts, clamp order intents, and produce projected candles so the
    dashboard can display counterfactual price action.
    """

    def __init__(
        self,
        agents: Sequence[LLMAgent],
        seed: Optional[int] = None,
    ):
        if not agents:
            raise ValueError("At least one LLMAgent is required")
        self._agents = list(agents)
        self._rng = np.random.default_rng(seed)

    # ------------------------------------------------------------------ public
    def run(
        self,
        scenario_text: str,
        steps: int = 20,
    ) -> List[ScenarioImpact]:
        impacts = extract_impact_candidates(scenario_text, top_n=3)
        if not impacts:
            # Fallback to a broad-market trio so the UI has something to render.
            impacts = [("SPY", 0.4), ("QQQ", 0.35), ("DIA", 0.3)]

        impacts_out: List[ScenarioImpact] = []

        for ticker, weight in impacts:
            base = self._bootstrap_candles(ticker)
            runner = ScenarioRunner(seed=int(self._rng.integers(0, 10_000)))
            runner.bootstrap(base)

            drift, vol = self._scenario_params(weight)
            projection = runner.project(
                scenario="headline",
                steps=steps,
                drift=drift,
                vol=vol,
                params={"base_volume": float(base["volume"].iloc[-1])},
            )

            last_close = float(base["close"].iloc[-1])
            llm_orders = self._collect_orders(
                scenario_text=scenario_text,
                ticker=ticker,
                last_price=last_close,
                drift=drift,
                vol=vol,
            )

            impacts_out.append(
                ScenarioImpact(
                    ticker=ticker,
                    score=weight,
                    orders=llm_orders,
                    projection=projection,
                )
            )

        return impacts_out

    # ----------------------------------------------------------------- helpers
    def _collect_orders(
        self,
        scenario_text: str,
        ticker: str,
        last_price: float,
        drift: float,
        vol: float,
    ) -> List[Order]:
        """
        Synthesise a simple JSON intent describing how personas react to the
        scenario. In a production setting you'd swap this heuristic with an LLM
        call; we still route through the LLMAgent to benefit from its risk guards.
        """
        sentiments = "BUY" if drift >= 0 else "SELL"
        qty = max(10.0, abs(drift) * 10_000)
        response = json.dumps(
            {
                "scenario": scenario_text,
                "orders": [
                    {
                        "symbol": ticker,
                        "side": sentiments,
                        "qty": qty,
                        "limit": last_price * (1 + drift),
                    }
                ],
            }
        )

        orders: List[Order] = []
        price_lookup = {ticker: last_price}
        for agent in self._agents:
            orders.extend(agent.parse_response(response, price_lookup=price_lookup))
        return orders

    def _bootstrap_candles(self, ticker: str) -> pd.DataFrame:
        """
        Produce a short intraday history so ScenarioRunner has something to
        extend. This synthesises data but keeps variance tied to the RNG seed so
        tests remain deterministic.
        """
        now = datetime.utcnow().replace(second=0, microsecond=0)
        periods = 30
        index = pd.date_range(now - timedelta(minutes=periods - 1), periods=periods, freq="1min")

        base_price = 100 + self._rng.normal(0, 5)
        noise = self._rng.normal(0, 0.3, size=periods).cumsum()
        close = base_price + noise
        open_ = np.concatenate(([close[0]], close[:-1]))
        high = np.maximum(open_, close) + abs(self._rng.normal(0, 0.2, size=periods))
        low = np.minimum(open_, close) - abs(self._rng.normal(0, 0.2, size=periods))
        volume = np.abs(self._rng.normal(1_000_000, 50_000, size=periods))

        frame = pd.DataFrame(
            {
                "open": open_,
                "high": high,
                "low": low,
                "close": close,
                "volume": volume,
            },
            index=index,
        )
        frame.index.name = "timestamp"
        return frame

    def _scenario_params(self, weight: float) -> tuple[float, float]:
        """
        Convert an impact weight into a crude drift/vol pair. Positive drift means
        price appreciation; negative means sell-off.
        """
        # Weight in [0, 1]; map to drift between -4% and +4% via centered scaling.
        drift = (weight - 0.5) * 0.08
        vol = 0.02 + (1 - abs(weight - 0.5)) * 0.03
        return drift, vol

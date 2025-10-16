from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from src.agents.llm import LLMAgent
from src.core.types import Order
from src.data.events import context
from src.data.events.analog_index import aggregate_metrics, match_analogs
from src.data.events.scenario_mapping import extract_impact_candidates
from src.data.news.polygon_news import fetch_recent_news
from src.data.pricing import polygon
from src.sim.calibration import get_calibrator
from src.sim.scenario_runner import ScenarioRunner


@dataclass
class ScenarioImpact:
    ticker: str
    score: float
    orders: List[Order]
    projection: pd.DataFrame
    baseline_price: float
    projected_price: float
    current_price: float
    analogs: List[Dict[str, object]]
    analog_metrics: Optional[Dict[str, float]]
    news: List[Dict[str, object]]


def _load_baseline_stats() -> Dict[str, Dict[str, float]]:
    stats_path = Path(__file__).resolve().parent.parent / "data" / "market" / "baseline_stats.json"
    if not stats_path.exists():
        return {}
    try:
        data = json.loads(stats_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    table: Dict[str, Dict[str, float]] = {}
    for entry in data:
        symbol = entry.get("symbol")
        if not symbol:
            continue
        cleaned = {k: float(v) for k, v in entry.items() if k != "symbol" and isinstance(v, (int, float))}
        table[symbol.upper()] = cleaned
    return table


BASELINE_STATS = _load_baseline_stats()
LOG_ROOT = Path(os.getenv("MARKETTWIN_LOG_DIR", Path.cwd() / "logs"))
LOG_ROOT.mkdir(parents=True, exist_ok=True)
SCENARIO_LOG_PATH = LOG_ROOT / "scenarios.log"


class ScenarioService:
    """Run scenario evaluations using Grok output and calibrated price dynamics."""

    def __init__(
        self,
        agents: Sequence[LLMAgent],
        seed: Optional[int] = None,
        baseline_stats: Optional[Mapping[str, Mapping[str, float]]] = None,
    ):
        if not agents:
            raise ValueError("At least one LLMAgent is required")
        self._agents = list(agents)
        self._rng = np.random.default_rng(seed)
        self._baseline_stats: Dict[str, Dict[str, float]] = {
            k: dict(v) for k, v in (baseline_stats or BASELINE_STATS).items()
        }
        self._calibrator = get_calibrator()

    def run(self, scenario_text: str, steps: int = 20) -> List[ScenarioImpact]:
        impacts_raw = extract_impact_candidates(scenario_text, top_n=3)
        if not impacts_raw:
            impacts_raw = [("SPY", 0.3), ("QQQ", 0.25), ("DIA", 0.2)]

        sentiment = context.estimate_sentiment(scenario_text.lower())
        log_entries: List[Dict[str, object]] = []
        impacts: List[ScenarioImpact] = []

        analog_matches = match_analogs(
            scenario_text,
            [symbol for symbol, _ in impacts_raw],
            top_n=4,
        )
        analog_stats = aggregate_metrics(analog_matches)

        for ticker, weight in impacts_raw:
            base = self._bootstrap_candles(ticker)
            runner = ScenarioRunner(seed=int(self._rng.integers(0, 10_000)))
            runner.bootstrap(base)

            step_minutes = self._infer_step_minutes(base)
            drift, vol, skew, kurtosis = self._scenario_params(ticker, weight, sentiment, step_minutes)
            stats = self._baseline_stats.get(ticker.upper())
            base_volume = stats["adv"] / 390 if stats and stats.get("adv") else float(base["volume"].iloc[-1])

            projection = runner.project(
                scenario="headline",
                steps=steps,
                drift=drift,
                vol=vol,
                params={"base_volume": float(base_volume), "skew": skew, "kurtosis": kurtosis},
            )

            baseline_price = float(base["close"].iloc[-1])
            projected_price = float(projection["close"].iloc[-1]) if not projection.empty else baseline_price
            current_price = polygon.get_last_price(ticker) or baseline_price

            llm_orders = self._collect_orders(
                scenario_text=scenario_text,
                ticker=ticker,
                last_price=baseline_price,
                drift=drift,
                vol=vol,
            )

            ticker_upper = ticker.upper()
            analogs = analog_matches.get(ticker_upper, [])
            analog_metric = analog_stats.get(ticker_upper)
            
            try:
                news = fetch_recent_news(ticker_upper, limit=3)
            except Exception:
                news = []

            impacts.append(
                ScenarioImpact(
                    ticker=ticker,
                    score=weight,
                    orders=llm_orders,
                    projection=projection,
                    baseline_price=baseline_price,
                    projected_price=projected_price,
                    current_price=current_price,
                    analogs=analogs,
                    analog_metrics=analog_metric,
                    news=news,
                )
            )

            log_entries.append(
                {
                    "ticker": ticker,
                    "score": weight,
                    "drift": drift,
                    "vol": vol,
                    "baseline_price": baseline_price,
                    "projected_price": projected_price,
                    "current_price": current_price,
                    "orders": [order.__dict__ for order in llm_orders],
                    "analogs": analogs,
                    "analog_metrics": analog_metric,
                }
            )

        self._log_scenario(scenario_text, sentiment, log_entries)
        return impacts

    def _collect_orders(
        self,
        scenario_text: str,
        ticker: str,
        last_price: float,
        drift: float,
        vol: float,
    ) -> List[Order]:
        side = "BUY" if drift >= 0 else "SELL"
        stats = self._baseline_stats.get(ticker.upper(), {})
        adv = stats.get("adv", 10_000_000)
        base_qty = max(5.0, adv * 0.015 / max(last_price, 1.0))
        directional_qty = base_qty * (0.6 + min(0.4, abs(drift) * 15))

        drift_abs = max(abs(drift), 0.002)
        direction = 1 if side == "BUY" else -1
        exit_side = "SELL" if side == "BUY" else "BUY"

        entry_pullback = min(0.004, 0.2 * drift_abs)
        initial_limit = last_price * (1 - direction * entry_pullback)

        breakout_trigger_move = 0.45 * drift_abs + 0.003
        breakout_trigger = last_price * (1 + direction * breakout_trigger_move)
        breakout_limit = last_price * (1 + direction * (breakout_trigger_move + 0.0015))

        tp_move = max(0.012, drift_abs * 1.6)
        take_profit_price = last_price * (1 + direction * tp_move)

        stop_move = max(0.006, drift_abs * 0.8)
        stop_trigger = last_price * (1 - direction * stop_move)

        staged_entry = {
            "symbol": ticker,
            "side": side,
            "qty": directional_qty,
            "order_type": "LMT",
            "limit": initial_limit,
            "stage": "core",
            "condition": {
                "type": "scale_in",
                "comment": "Stage entries with pullback then breakout confirmation",
            },
            "notes": "Auto-generated staged ladder",
            "stages": [
                {
                    "stage": "initial",
                    "qty": directional_qty * 0.6,
                    "order_type": "LMT",
                    "limit": initial_limit,
                    "notes": "post near baseline pullback",
                },
                {
                    "stage": "momentum_add",
                    "qty": directional_qty * 0.4,
                    "order_type": "STOP_LIMIT",
                    "trigger": breakout_trigger,
                    "limit": breakout_limit,
                    "notes": "add only if price confirms momentum",
                },
            ],
        }

        take_profit = {
            "symbol": ticker,
            "side": exit_side,
            "qty": directional_qty * 0.5,
            "order_type": "LMT",
            "limit": take_profit_price,
            "stage": "take_profit",
            "condition": {
                "type": "target",
                "comment": "Scale out into projected move",
            },
        }

        protective_stop = {
            "symbol": ticker,
            "side": exit_side,
            "qty": directional_qty,
            "order_type": "STOP",
            "trigger": stop_trigger,
            "time_in_force": "GTC",
            "stage": "protect",
            "condition": {
                "type": "risk_guardrail",
                "comment": "Hard stop to cap downside",
            },
        }

        order_payload = {
            "scenario": scenario_text,
            "orders": [staged_entry, protective_stop, take_profit],
            "notes": "Staged ladder with attached guard rails",
        }

        response = json.dumps(order_payload)
        orders: List[Order] = []
        price_lookup = {ticker: last_price}
        for agent in self._agents:
            orders.extend(agent.parse_response(response, price_lookup=price_lookup))
        return orders

    def _bootstrap_candles(self, ticker: str) -> pd.DataFrame:
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

    def _infer_step_minutes(self, frame: pd.DataFrame) -> float:
        if len(frame.index) >= 2:
            delta = frame.index[-1] - frame.index[-2]
            return max(delta.total_seconds() / 60.0, 1.0)
        return 1.0

    def _scenario_params(
        self,
        ticker: str,
        weight: float,
        sentiment: float,
        step_minutes: float,
    ) -> Tuple[float, float, float, float]:
        stats = self._baseline_stats.get(ticker.upper())
        direction = 1 if weight >= 0 else -1
        magnitude = min(1.0, abs(weight))
        signal = sentiment if abs(sentiment) > 0.05 else direction * magnitude

        drift_cal, vol_cal, skew, kurtosis = self._calibrator.calibrate(weight)

        drift_daily = drift_cal
        vol_daily = vol_cal

        if stats:
            if direction >= 0:
                drift_stats = stats.get("avg_drift_positive", 0.015)
            else:
                drift_stats = -abs(stats.get("avg_drift_negative", 0.015))
            drift_daily = drift_daily + drift_stats * (0.8 + magnitude)
            liquidity_factor = min(1.8, max(0.6, stats.get("adv", 1_000_000) / 50_000_000))
            vol_daily = max(
                vol_daily,
                stats.get("volatility", 0.02) * (0.8 + magnitude) * liquidity_factor,
            )
        else:
            vol_daily = max(vol_daily, 0.02 * (0.8 + magnitude))

        drift_daily += drift_daily * signal * 0.2

        trading_minutes = 390.0
        dt = max(step_minutes, 1.0) / trading_minutes
        drift_step = float(np.clip(drift_daily, -0.25, 0.25)) * dt
        vol_step = float(max(1e-6, vol_daily)) * (dt ** 0.5)

        return drift_step, vol_step, skew, kurtosis

    def _log_scenario(self, scenario_text: str, sentiment: float, impacts: List[Dict[str, object]]) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "scenario": scenario_text,
            "sentiment": sentiment,
            "impacts": impacts,
        }
        try:
            with SCENARIO_LOG_PATH.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(entry) + "\n")
        except Exception:
            pass

# src/agents/institutional/ark_agent.py
from __future__ import annotations
"""
ARK agent: mirrors ETF target weights and nudges toward them each step.
- Robust to column-name drift in ARK CSVs
- Falls back to a tiny local holding if fetch fails
- Tunable sizing rails (aum_multiplier, max_symbol_weight, per_tick_cap)
- Updates cash/position on fills so PnL/qty make sense
"""

from typing import Optional, Dict
import pandas as pd

from src.agents.institutional.base import InstitutionalAgentBase, DesiredOrder
from src.data.institutional.ark import fetch_ark_holdings


def _ticker_map(t: str) -> str:
    return str(t).strip().upper()


class ARKAgent(InstitutionalAgentBase):
    def __init__(
        self,
        agent_id: str = "ark-arkk",
        etf: str = "ARKK",
        cash: float = 250_000.0,
        *,
        aum_multiplier: float = 1.0,      # scale “fund equity” vs. agent equity
        max_symbol_weight: float = 0.10,  # hard cap per symbol as % of fund equity
        per_tick_cap: float = 25.0,       # max shares to adjust per step
    ):
        super().__init__(agent_id=agent_id, cash=cash, max_trade_per_tick=per_tick_cap)
        self.etf = etf
        self.aum_multiplier = float(aum_multiplier)
        self.max_symbol_weight = float(max_symbol_weight)

        self._last_holdings: Optional[pd.DataFrame] = None

        # Ensure these exist in case base doesn’t set them
        if not hasattr(self, "position"):
            self.position: Dict[str, float] = {}
        if not hasattr(self, "cash"):
            self.cash = float(cash)

        self.last_live_symbol: Optional[str] = None
        if not hasattr(self, "trades"):
            self.trades = 0

        # Refresh logging throttle
        self._refresh_count = 0
        self._print_every = 24  # roughly “daily” in a 1-step=~1h sim; tweak as needed

    # ---------- Helpers ----------

    def _fallback_holdings(self) -> pd.DataFrame:
        """Minimal fallback so the agent exhibits behavior immediately."""
        return pd.DataFrame({"ticker": ["TSLA"], "weight (%)": [5.0]})

    # ---------- Data refresh ----------

    def update_holdings(self) -> None:
        """Fetch ARK holdings and cache them locally (with fallback)."""
        data: Dict[str, pd.DataFrame] = fetch_ark_holdings()
        df = (data or {}).get(self.etf)
        if df is None or df.empty:
            df = self._fallback_holdings()
        self._last_holdings = df

        # Throttled debug print
        self._refresh_count += 1
        if self._refresh_count == 1 or (self._refresh_count % self._print_every == 0):
            try:
                sample = df[["ticker", "weight (%)"]].head(3).to_dict("records")
                print(f"[ARK] {self.etf} holdings loaded:", sample)
            except Exception:
                pass

    # ---------- Trading logic ----------

    def translate_holdings_to_orders(
        self,
        live_symbol: str,
        live_price: float,
    ) -> Optional[DesiredOrder]:
        """
        Return a DesiredOrder nudging toward ARK's target weight for live_symbol.
        """
        if self._last_holdings is None or live_price <= 0:
            return None

        # Normalize columns for resilient lookups
        df: pd.DataFrame = self._last_holdings.copy()
        df.columns = [str(c).strip().lower() for c in df.columns]

        weight_col = next(
            (c for c in ["weight (%)", "weight %", "weight", "portfolio weight"] if c in df.columns),
            None,
        )
        ticker_col = next(
            (c for c in ["ticker", "ticker_symbol", "holding ticker", "ticker symbol"] if c in df.columns),
            None,
        )
        if weight_col is None or ticker_col is None:
            return None

        row = df.loc[df[ticker_col].astype(str).str.upper() == _ticker_map(live_symbol)]
        if row.empty:
            return None

        # target weight %
        try:
            weight_pct = float(row.iloc[0][weight_col])
        except Exception:
            return None

        # Portfolio equity (single-symbol approximation)
        qty_total = sum(self.position.values()) if isinstance(self.position, dict) else 0.0
        portfolio_equity = float(self.cash + qty_total * live_price)
        fund_equity = max(1.0, portfolio_equity) * self.aum_multiplier

        # Convert target weight to target notional, then cap per-symbol weight
        raw_target_value = (weight_pct / 100.0) * fund_equity
        cap_value = self.max_symbol_weight * fund_equity
        target_value = min(raw_target_value, cap_value)
        target_qty = target_value / live_price

        current_qty = float(self.position.get(live_symbol, 0.0))
        delta = target_qty - current_qty

        # bound the per-step change
        step = max(-self.max_trade_per_tick, min(self.max_trade_per_tick, delta))
        if abs(step) < 1e-6:
            return None

        # remember symbol for on_fill
        self.last_live_symbol = live_symbol

        return DesiredOrder(
            symbol=live_symbol,
            side="BUY" if step > 0 else "SELL",
            qty=abs(step),
        )

    # ---------- fills & valuation ----------

    def on_fill(self, fill_price: float, qty: float, side: str) -> None:
        sym = self.last_live_symbol
        if not sym:
            return
        if side == "BUY":
            self.position[sym] = self.position.get(sym, 0.0) + qty
            self.cash -= qty * fill_price
        else:
            self.position[sym] = self.position.get(sym, 0.0) - qty
            self.cash += qty * fill_price
        self.trades = getattr(self, "trades", 0) + 1

    def mark_to_market(self, price: float) -> float:
        qty_total = sum(self.position.values()) if isinstance(self.position, dict) else 0.0
        return float(self.cash + qty_total * price)


# Back-compat alias
ArkAgent = ARKAgent
__all__ = ["ARKAgent", "ArkAgent", "DesiredOrder"]

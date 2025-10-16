from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict
import pandas as pd

@dataclass
class DesiredOrder:
    symbol: str         # e.g., "TSLA" or "X:BTCUSD"
    side: str           # "BUY" or "SELL"
    qty: float          # desired shares/units

class InstitutionalAgentBase:
    def __init__(self, agent_id: str, cash: float = 250_000.0, max_trade_per_tick: float = 500.0):
        self.agent_id = agent_id
        self.cash = cash
        self.position: Dict[str, float] = {}
        self.max_trade_per_tick = max_trade_per_tick
        self._last_holdings: Optional[pd.DataFrame] = None

    def update_holdings(self) -> None:
        """Override: refresh self._last_holdings (pandas DataFrame)."""
        pass

    def translate_holdings_to_orders(self, live_symbol: str, live_price: float) -> Optional[DesiredOrder]:
        """Override: map current holdings delta to a one-tick order for this symbol."""
        return None

    # simple execution callback from env
    def on_fill(self, symbol: str, side: str, qty: float, price: float):
        if side == "BUY":
            self.cash -= qty * price
            self.position[symbol] = self.position.get(symbol, 0.0) + qty
        else:
            self.cash += qty * price
            self.position[symbol] = self.position.get(symbol, 0.0) - qty

    def equity(self, mark_prices: Dict[str, float]) -> float:
        eq = self.cash
        for sym, qty in self.position.items():
            eq += qty * mark_prices.get(sym, 0.0)
        return eq

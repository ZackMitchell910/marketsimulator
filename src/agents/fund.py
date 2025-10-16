from __future__ import annotations
from typing import List
import numpy as np
from .base import BaseAgent
from src.core.types import Order

class FundAgent(BaseAgent):
    """Simple mean-reversion fund:
    - Buys when price < EMA(span) by threshold
    - Sells when price > EMA(span) by threshold
    Position size scales with deviation.
    """
    def __init__(self, agent_id: str, span: int = 30, threshold_bps: float = 20, max_qty: float = 100):
        super().__init__(agent_id)
        self.span = span
        self.threshold = threshold_bps / 10_000.0  # convert bps to fraction
        self.max_qty = max_qty
        self._ema = None

    def observe(self, t: int, price_history: np.ndarray) -> None:
        if len(price_history) < 2:
            return
        # Fast incremental EMA (fallback to full calc for simplicity)
        alpha = 2 / (self.span + 1.0)
        if self._ema is None:
            self._ema = price_history[-1]
        else:
            self._ema = alpha * price_history[-1] + (1 - alpha) * self._ema

    def decide(self, t: int, price: float) -> List[Order]:
        if self._ema is None:
            return []
        dev = (price - self._ema) / self._ema  # positive if price > ema
        orders: List[Order] = []
        if dev > self.threshold and self.state.qty > -self.max_qty:
            # price is rich -> sell
            qty = min(10.0, self.max_qty + self.state.qty)  # if short, limit size
            if qty > 0:
                orders.append(Order(agent_id=self.state.agent_id, side="SELL", qty=qty))
        elif dev < -self.threshold and self.state.qty < self.max_qty:
            # price is cheap -> buy
            qty = min(10.0, self.max_qty - self.state.qty)
            if qty > 0:
                orders.append(Order(agent_id=self.state.agent_id, side="BUY", qty=qty))
        return orders

from __future__ import annotations
from typing import List
import numpy as np
from .base import BaseAgent
from src.core.types import Order

class RetailAgent(BaseAgent):
    """Simple momentum-chasing retail cluster:
    - If last k returns are positive, buy small
    - If last k returns are negative, sell small
    """
    def __init__(self, agent_id: str, lookback: int = 5, trade_qty: float = 2.0, max_qty: float = 40):
        super().__init__(agent_id)
        self.lookback = lookback
        self.trade_qty = trade_qty
        self.max_qty = max_qty
        self._last_rets = None

    def observe(self, t: int, price_history: np.ndarray) -> None:
        if len(price_history) > 1:
            rets = np.diff(price_history[-(self.lookback+1):]) / price_history[-(self.lookback+1):-1]
            self._last_rets = rets

    def decide(self, t: int, price: float) -> List[Order]:
        if self._last_rets is None:
            return []
        momentum = self._last_rets.mean()
        orders: List[Order] = []
        if momentum > 0 and self.state.qty < self.max_qty:
            qty = min(self.trade_qty, self.max_qty - self.state.qty)
            orders.append(Order(agent_id=self.state.agent_id, side="BUY", qty=qty))
        elif momentum < 0 and self.state.qty > -self.max_qty:
            qty = min(self.trade_qty, self.max_qty + self.state.qty)  # if short, cap
            orders.append(Order(agent_id=self.state.agent_id, side="SELL", qty=qty))
        return orders

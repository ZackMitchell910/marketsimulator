from __future__ import annotations
from dataclasses import dataclass
from typing import List
import numpy as np
from src.core.types import Order

@dataclass
class AgentState:
    agent_id: str
    cash: float = 100_000.0
    qty: float = 0.0
    trades: int = 0

class BaseAgent:
    def __init__(self, agent_id: str):
        self.state = AgentState(agent_id=agent_id)

    def observe(self, t: int, price_history: np.ndarray) -> None:
        """Receive latest observations. Override if needed."""
        pass

    def decide(self, t: int, price: float) -> List[Order]:
        """Return a list of orders to submit at time t."""
        return []

    def on_fill(self, fill_price: float, qty: float, side: str) -> None:
        if qty == 0:
            return
        self.state.trades += 1
        if side == "BUY":
            self.state.cash -= fill_price * qty
            self.state.qty += qty
        elif side == "SELL":
            self.state.cash += fill_price * qty
            self.state.qty -= qty

    def mark_to_market(self, price: float) -> float:
        return self.state.cash + self.state.qty * price

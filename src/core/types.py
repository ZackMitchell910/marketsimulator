from __future__ import annotations
from dataclasses import dataclass
from typing import Literal, Optional

Side = Literal["BUY", "SELL"]

@dataclass
class Order:
    agent_id: str
    side: Side
    qty: float  # positive size
    price_limit: Optional[float] = None  # optional limit price

@dataclass
class Position:
    qty: float = 0.0
    cash: float = 0.0

    @property
    def exposure(self) -> float:
        return self.qty

@dataclass
class Fill:
    agent_id: str
    side: Side
    qty: float
    price: float

@dataclass
class Metrics:
    agent_id: str
    pnl: float
    trades: int

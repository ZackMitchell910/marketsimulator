from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Literal, Optional

OrderSide = Literal["BUY", "SELL"]
Side = OrderSide  # Backwards compatibility alias
OrderType = Literal["LMT", "MKT", "IOC", "STOP", "STOP_LIMIT", "TRAIL", "MIT"]
TimeInForce = Literal["DAY", "IOC", "GTC", "FOK"]

@dataclass
class Order:
    agent_id: str
    side: OrderSide
    qty: float  # positive size
    price_limit: Optional[float] = None  # optional limit price
    symbol: Optional[str] = None  # optional instrument identifier
    order_type: OrderType = "MKT"
    time_in_force: Optional[TimeInForce] = None
    stage: Optional[str] = None
    condition: Optional[str] = None
    trigger: Optional[float] = None
    meta: Optional[Dict[str, Any]] = None

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
    side: OrderSide
    qty: float
    price: float

@dataclass
class Metrics:
    agent_id: str
    pnl: float
    trades: int

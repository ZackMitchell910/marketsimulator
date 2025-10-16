from __future__ import annotations
from dataclasses import dataclass

@dataclass
class MarketTick:
    t: int
    price: float
    bid: float
    ask: float
    spread: float

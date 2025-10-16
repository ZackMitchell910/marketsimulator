"""Order/Trade primitives (placeholder)."""
from enum import Enum, auto

class Side(Enum): BUY=auto(); SELL=auto()
class TIF(Enum): DAY=auto(); IOC=auto()

class Order: ...
class Trade: ...

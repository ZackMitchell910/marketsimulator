from __future__ import annotations
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple
from collections import deque


@dataclass
class LevelOrder:
    agent_id: str
    qty: float
    ts_idx: int


@dataclass
class BookSide:
    levels: Dict[float, Deque[LevelOrder]] = field(default_factory=dict)

    def add(self, px: float, o: LevelOrder):
        q = self.levels.setdefault(px, deque())
        q.append(o)

    def cancel(self, px: float, agent_id: str) -> float:
        q = self.levels.get(px)
        if not q:
            return 0.0
        keep, removed = deque(), 0.0
        while q:
            x = q.popleft()
            if x.agent_id == agent_id:
                removed += x.qty
            else:
                keep.append(x)
        if keep:
            self.levels[px] = keep
        else:
            self.levels.pop(px, None)
        return removed

    def best_prices(self, is_bid: bool, depth: int) -> List[float]:
        if not self.levels:
            return []
        keys = sorted(self.levels.keys(), reverse=is_bid)
        return [k for k in keys if self.levels[k]][:depth]

    def sweep(
        self, qty: float, is_buy: bool
    ) -> List[Tuple[float, float, List[LevelOrder]]]:
        """
        Match marketable qty against opposite side.
        Returns list of (px, traded_qty, fills).
        """
        traded: List[Tuple[float, float, List[LevelOrder]]] = []
        prices = sorted(self.levels.keys(), reverse=is_buy)
        remaining = qty
        for px in prices:
            if remaining <= 1e-12:
                break
            q = self.levels.get(px)
            if not q:
                continue
            lvl_fills: List[LevelOrder] = []
            lvl_qty = 0.0
            while q and remaining > 1e-12:
                lo = q[0]
                take = min(lo.qty, remaining)
                lvl_fills.append(LevelOrder(lo.agent_id, take, lo.ts_idx))
                lo.qty -= take
                remaining -= take
                lvl_qty += take
                if lo.qty <= 1e-12:
                    q.popleft()
            if not q:
                self.levels.pop(px, None)
            if lvl_qty > 0:
                traded.append((px, lvl_qty, lvl_fills))
        return traded


@dataclass
class LimitOrderBook:
    bids: BookSide = field(default_factory=BookSide)
    asks: BookSide = field(default_factory=BookSide)
    tick_size: float = 0.01
    max_depth: int = 10

    def _round(self, px: float) -> float:
        return round(px / self.tick_size) * self.tick_size

    def add_limit(self, side: str, px: float, qty: float, agent_id: str, ts_idx: int):
        px = self._round(px)
        if side.upper() == "BUY":
            self.bids.add(px, LevelOrder(agent_id, qty, ts_idx))
        else:
            self.asks.add(px, LevelOrder(agent_id, qty, ts_idx))

    def cancel(self, side: str, px: float, agent_id: str) -> float:
        px = self._round(px)
        return (self.bids if side.upper() == "BUY" else self.asks).cancel(px, agent_id)

    def best_bid(self) -> Optional[float]:
        ps = self.bids.best_prices(True, 1)
        return ps[0] if ps else None

    def best_ask(self) -> Optional[float]:
        ps = self.asks.best_prices(False, 1)
        return ps[0] if ps else None

    def top_levels(self) -> Dict[str, List[Tuple[float, float]]]:
        out = {"bids": [], "asks": []}
        for is_bid, side in [(True, self.bids), (False, self.asks)]:
            prices = side.best_prices(is_bid, self.max_depth)
            for p in prices:
                qty = sum(lo.qty for lo in side.levels[p])
                (out["bids"] if is_bid else out["asks"]).append((p, qty))
        return out

    def market_order(
        self, side: str, qty: float
    ) -> List[Tuple[str, float, float, str]]:
        is_buy = side.upper() == "BUY"
        sidebook = self.asks if is_buy else self.bids
        trades = sidebook.sweep(qty, is_buy)
        fills: List[Tuple[str, float, float, str]] = []
        for px, _tq, makers in trades:
            for m in makers:
                fills.append((side.upper(), px, m.qty, m.agent_id))
        return fills

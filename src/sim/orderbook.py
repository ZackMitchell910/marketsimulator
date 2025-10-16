from __future__ import annotations

from dataclasses import dataclass
from collections import deque
from typing import Deque, Dict, List, Optional, Tuple

from src.core.types import Order, OrderType, Side

_EPS = 1e-12


@dataclass
class Trade:
    price: float
    qty: float
    taker_id: str
    maker_id: str
    taker_side: Side
    symbol: Optional[str]


@dataclass
class _BookOrder:
    agent_id: str
    qty: float
    price: float
    symbol: Optional[str]
    sequence: int


class _BookSide:
    def __init__(self, is_bid: bool):
        self._is_bid = is_bid
        self._levels: Dict[float, Deque[_BookOrder]] = {}

    def add(self, price: float, order: _BookOrder) -> None:
        level = self._levels.setdefault(price, deque())
        level.append(order)

    def best_price(self) -> Optional[float]:
        if not self._levels:
            return None
        prices = sorted(self._levels.keys(), reverse=self._is_bid)
        for price in prices:
            level = self._levels.get(price)
            if level:
                return price
            self._levels.pop(price, None)
        return None

    def remove_if_empty(self, price: float) -> None:
        level = self._levels.get(price)
        if level is not None and not level:
            self._levels.pop(price, None)

    def levels(self) -> Dict[float, Deque[_BookOrder]]:
        return self._levels

    def iterate_prices(self) -> List[float]:
        return sorted(self._levels.keys(), reverse=self._is_bid)


class OrderBook:
    """
    Price-time priority limit order book supporting limit, market, and IOC orders.
    """

    def __init__(self, tick_size: float = 0.01):
        if tick_size <= 0:
            raise ValueError("tick_size must be positive")
        self._tick = float(tick_size)
        self._bids = _BookSide(is_bid=True)
        self._asks = _BookSide(is_bid=False)
        self._sequence = 0

    # ------------------------------------------------------------------ public
    def submit(self, order: Order) -> List[Trade]:
        """
        Process an incoming order. Returns a list of trades produced while the
        order crossed the book. Any residual limit quantity is queued.
        """
        if order.qty <= 0:
            return []

        side = order.side.upper()
        inferred_type = "LMT" if order.price_limit is not None else "MKT"
        declared = (order.order_type or inferred_type).upper()
        if declared not in {"LMT", "MKT", "IOC"}:
            raise ValueError(f"Unsupported order_type: {declared}")
        order_type: OrderType = declared  # type: ignore[assignment]

        price_limit = self._normalize_price(order.price_limit)
        remaining = float(order.qty)
        trades: List[Trade] = []

        taker_side = self._asks if side == "BUY" else self._bids
        book_side = self._bids if side == "BUY" else self._asks

        if order_type == "LMT" and price_limit is None:
            raise ValueError("Limit orders require price_limit")
        if order_type == "IOC" and price_limit is None:
            order_type = "MKT"

        while remaining > _EPS:
            best_price = taker_side.best_price()
            if best_price is None:
                break
            if not self._is_marketable(side, best_price, price_limit, order_type):
                break

            level = taker_side.levels().get(best_price)
            if not level:
                taker_side.remove_if_empty(best_price)
                continue

            resting = level[0]
            trade_qty = min(remaining, resting.qty)
            trades.append(
                Trade(
                    price=best_price,
                    qty=trade_qty,
                    taker_id=order.agent_id,
                    maker_id=resting.agent_id,
                    taker_side=side,  # type: ignore[arg-type]
                    symbol=order.symbol or resting.symbol,
                )
            )

            remaining -= trade_qty
            resting.qty -= trade_qty

            if resting.qty <= _EPS:
                level.popleft()
            if not level:
                taker_side.remove_if_empty(best_price)

        if remaining > _EPS and self._should_rest(order_type):
            if price_limit is None:
                raise ValueError("Limit/IOC orders require a price_limit to rest")
            self._sequence += 1
            resting_order = _BookOrder(
                agent_id=order.agent_id,
                qty=remaining,
                price=price_limit,
                symbol=order.symbol,
                sequence=self._sequence,
            )
            book_side.add(price_limit, resting_order)

        return trades

    def top_of_book(self) -> Dict[str, Optional[Tuple[float, float]]]:
        bids = self._aggregate(self._bids, levels=1)
        asks = self._aggregate(self._asks, levels=1)
        return {
            "bid": bids[0] if bids else None,
            "ask": asks[0] if asks else None,
        }

    def depth(self, levels: int = 5) -> Dict[str, List[Tuple[float, float]]]:
        if levels <= 0:
            return {"bids": [], "asks": []}
        return {
            "bids": self._aggregate(self._bids, levels=levels),
            "asks": self._aggregate(self._asks, levels=levels),
        }

    # ----------------------------------------------------------------- helpers
    def _aggregate(self, side: _BookSide, levels: int) -> List[Tuple[float, float]]:
        out: List[Tuple[float, float]] = []
        for price in side.iterate_prices():
            level = side.levels().get(price)
            if not level:
                continue
            qty = sum(max(0.0, o.qty) for o in level)
            if qty > _EPS:
                out.append((price, qty))
            if len(out) >= levels:
                break
        return out

    def _is_marketable(
        self,
        side: Side,
        best_price: float,
        price_limit: Optional[float],
        order_type: OrderType,
    ) -> bool:
        if order_type == "MKT":
            return True
        if price_limit is None:
            return False
        if side == "BUY":
            return best_price <= price_limit + _EPS
        return best_price >= price_limit - _EPS

    def _should_rest(self, order_type: OrderType) -> bool:
        return order_type == "LMT"

    def _normalize_price(self, price: Optional[float]) -> Optional[float]:
        if price is None:
            return None
        return round(price / self._tick) * self._tick

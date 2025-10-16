from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Mapping, Optional

from .base import BaseAgent
from src.core.types import Order


class LLMAgent(BaseAgent):
    """
    Lightweight wrapper around BaseAgent that prepares structured persona prompts,
    parses LLM JSON order intents, and enforces simple risk guards before emitting
    executable orders.
    """

    def __init__(
        self,
        agent_id: str,
        persona: Mapping[str, Any],
        risk_limits: Optional[Mapping[str, float]] = None,
    ):
        super().__init__(agent_id=agent_id)
        self.persona = dict(persona)
        self.risk_limits: Dict[str, float] = {
            "max_position": float("inf"),
            "max_order_notional": float("inf"),
            "max_notional": float("inf"),
        }
        if risk_limits:
            for key, value in risk_limits.items():
                if value is None:
                    continue
                self.risk_limits[key] = float(value)

    # --- Prompt construction -------------------------------------------------
    def serialize_prompt(
        self,
        market: Mapping[str, Any],
        portfolio: Mapping[str, Any],
        risk: Mapping[str, Any],
    ) -> str:
        """
        Create a structured JSON prompt that can be forwarded to an LLM.
        """
        payload = {
            "persona": self.persona,
            "market": market,
            "portfolio": portfolio,
            "risk": risk,
        }
        return json.dumps(payload, indent=2, sort_keys=True)

    # --- Response parsing ----------------------------------------------------
    def parse_response(
        self,
        response: str,
        price_lookup: Mapping[str, float],
    ) -> List[Order]:
        """
        Convert an LLM JSON blob into validated Order objects. Any malformed
        payloads are ignored, yielding an empty order list.
        """
        try:
            parsed = json.loads(response)
        except (json.JSONDecodeError, TypeError):
            return []

        intents: Iterable[Mapping[str, Any]] = parsed.get("orders", [])
        orders: List[Order] = []
        for intent in intents:
            symbol = intent.get("symbol")
            side = (intent.get("side") or "").upper()
            qty = intent.get("qty", intent.get("quantity"))
            price_limit = intent.get("limit")

            if not symbol or side not in {"BUY", "SELL"}:
                continue
            try:
                quantity = float(qty)
            except (TypeError, ValueError):
                continue
            if quantity <= 0:
                continue

            capped_qty = self._apply_risk_limits(
                side=side,
                requested_qty=quantity,
                price=price_lookup.get(symbol, 0.0),
            )
            if capped_qty <= 0:
                continue

            orders.append(
                Order(
                    agent_id=self.state.agent_id,
                    side=side,  # type: ignore[arg-type]
                    qty=capped_qty,
                    price_limit=float(price_limit) if price_limit is not None else None,
                )
            )
        return orders

    # --- Internal helpers ----------------------------------------------------
    def _apply_risk_limits(self, side: str, requested_qty: float, price: float) -> float:
        """
        Enforce coarse position and notional limits, returning a possibly-reduced
        quantity. Returns 0 if the order would breach limits entirely.
        """
        qty = max(0.0, float(requested_qty))

        # Position guard (symmetric long/short).
        max_position = self.risk_limits.get("max_position", float("inf"))
        if max_position < float("inf"):
            current = float(self.state.qty)
            room = self._position_room(side=side, current=current, limit=max_position)
            qty = min(qty, room)

        if qty <= 0.0:
            return 0.0

        if price > 0.0:
            max_order_notional = self.risk_limits.get("max_order_notional", float("inf"))
            if max_order_notional < float("inf"):
                qty = min(qty, max_order_notional / price)

            max_notional = self.risk_limits.get("max_notional", float("inf"))
            if max_notional < float("inf"):
                current_notional = abs(self.state.qty) * price
                remaining = max_notional - current_notional
                if remaining <= 0:
                    return 0.0
                qty = min(qty, remaining / price)

        return max(0.0, qty)

    @staticmethod
    def _position_room(side: str, current: float, limit: float) -> float:
        """How many additional units can we trade without exceeding limit."""
        if limit <= 0:
            return 0.0
        if side == "BUY":
            return max(0.0, limit - max(current, 0.0))
        # SELL path
        return max(0.0, limit - abs(min(current, 0.0)))


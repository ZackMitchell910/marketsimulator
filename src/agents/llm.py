from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Mapping, Optional

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError, field_validator

from .base import BaseAgent
from src.core.types import Order, OrderType, TimeInForce


_LOGGER = logging.getLogger(__name__)

DEFAULT_ORDER_TEMPLATES = [
    {
        "label": "Staged scale-in with protective stop",
        "stages": [
            {
                "stage": "initial",
                "order_type": "LMT",
                "sizing": "40%",
                "description": "Post a resting limit near fair value to begin the position.",
            },
            {
                "stage": "add",
                "order_type": "STOP_LIMIT",
                "sizing": "35%",
                "trigger_offset": "+0.6% vs baseline",
                "limit_offset": "+0.7% vs baseline",
                "description": "Only add when momentum confirms in our favour.",
            },
            {
                "stage": "trim",
                "order_type": "LMT",
                "sizing": "25%",
                "limit_offset": "+1.2% vs baseline",
                "description": "Scale out into strength once targets hit.",
            },
        ],
        "condition": "Attach a protective STOP 0.8% beyond baseline for the full size.",
    }
]

DEFAULT_GUIDELINES = [
    "Express orders as JSON with a top-level `orders` array.",
    "Each staged order leg should include `stage`, `qty`, and `order_type`.",
    "Include `trigger` for STOP or STOP_LIMIT legs and describe guardrails in `condition`.",
    "Always consider existing risk metrics before sizing new exposure.",
]


class OrderIntent(BaseModel):
    """Validated structure for an individual order intent coming from the LLM."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    symbol: str = Field(..., min_length=1, description="Instrument identifier")
    side: str = Field(..., description="BUY or SELL")
    qty: float = Field(..., gt=0, alias="quantity", description="Positive quantity")
    limit: Optional[float] = Field(
        default=None,
        validation_alias=AliasChoices("limit", "price_limit"),
        description="Optional limit price",
    )
    order_type: Optional[str] = Field(
        default=None,
        alias="type",
        validation_alias=AliasChoices("order_type", "type"),
        description="Optional order type hint",
    )
    time_in_force: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("time_in_force", "tif"),
        description="Optional time in force",
    )
    stage: Optional[str] = Field(
        default=None,
        description="Optional label describing staged execution leg",
    )
    condition: Optional[str] = Field(
        default=None,
        description="Optional free-form condition label",
    )
    trigger: Optional[float] = Field(
        default=None,
        validation_alias=AliasChoices("trigger", "trigger_price", "stop_price"),
        description="Optional trigger price for conditional orders",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Optional commentary for the leg",
    )

    @field_validator("symbol")
    @classmethod
    def _clean_symbol(cls, value: str) -> str:
        cleaned = (value or "").strip().upper()
        if not cleaned:
            raise ValueError("symbol required")
        return cleaned

    @field_validator("side")
    @classmethod
    def _normalize_side(cls, value: str) -> str:
        normalized = (value or "").strip().upper()
        if normalized not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")
        return normalized

    @field_validator("order_type")
    @classmethod
    def _normalize_order_type(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip().upper().replace("-", "_")
        if normalized not in {"MKT", "LMT", "IOC", "STOP", "STOP_LIMIT", "TRAIL", "MIT"}:
            raise ValueError("order_type must be one of MKT, LMT, IOC, STOP, STOP_LIMIT, TRAIL, MIT")
        return normalized

    @field_validator("time_in_force")
    @classmethod
    def _normalize_tif(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip().upper()
        if normalized not in {"DAY", "IOC", "GTC", "FOK"}:
            raise ValueError("time_in_force must be one of DAY, IOC, GTC, FOK")
        return normalized

    @field_validator("stage", "condition", "notes", mode="before")
    @classmethod
    def _strip_optional_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        cleaned = str(value).strip()
        return cleaned or None


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
        persona_profile = {
            "id": self.state.agent_id,
            "name": self.persona.get("name"),
            "description": self.persona.get("description"),
            "mandate": self.persona.get("mandate"),
            "style": self.persona.get("style"),
            "horizon": self.persona.get("horizon"),
            "risk_profile": self.persona.get("risk_profile"),
        }
        playbook = self.persona.get("playbook", [])
        order_templates = self.persona.get("order_templates") or DEFAULT_ORDER_TEMPLATES
        guidelines = self.persona.get("guidelines") or DEFAULT_GUIDELINES

        payload = {
            "persona": persona_profile,
            "guidelines": guidelines,
            "playbook": playbook,
            "order_templates": order_templates,
            "market_state": market,
            "portfolio_state": portfolio,
            "risk_state": risk,
            "response_schema": {
                "orders": [
                    {
                        "symbol": "TICKER",
                        "side": "BUY|SELL",
                        "qty": "float > 0",
                        "order_type": "MKT|LMT|IOC|STOP|STOP_LIMIT|TRAIL|MIT",
                        "limit": "optional float",
                        "trigger": "optional float",
                        "time_in_force": "optional DAY|IOC|GTC|FOK",
                        "stage": "optional stage label",
                        "condition": "optional short descriptor",
                        "notes": "optional commentary",
                        "stages": [
                            {
                                "stage": "entry|add|exit",
                                "qty": "float > 0",
                                "order_type": "same enum",
                                "limit": "optional",
                                "trigger": "optional",
                            }
                        ],
                    }
                ],
                "notes": "Optional trade rationale",
            },
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
            payload = json.loads(response)
        except (TypeError, ValueError):
            _LOGGER.warning("LLMAgent %s received non-JSON response", self.state.agent_id)
            return []

        if not isinstance(payload, Mapping):
            _LOGGER.warning(
                "LLMAgent %s received non-object payload: %s",
                self.state.agent_id,
                type(payload).__name__,
            )
            return []

        raw_orders = payload.get("orders", [])
        if not isinstance(raw_orders, list):
            _LOGGER.warning("LLMAgent %s payload missing 'orders' list", self.state.agent_id)
            return []

        orders: List[Order] = []
        for raw_intent in raw_orders:
            expanded_payloads = self._expand_order_payload(raw_intent)
            for expanded in expanded_payloads:
                condition_label, condition_meta = self._normalize_condition(expanded.get("condition"))
                working_payload = dict(expanded)
                if condition_label is not None:
                    working_payload["condition"] = condition_label
                elif "condition" in working_payload:
                    working_payload["condition"] = None

                try:
                    intent = OrderIntent.model_validate(working_payload)
                except ValidationError as exc:
                    _LOGGER.info(
                        "LLMAgent %s dropped malformed intent: %s | payload=%s",
                        self.state.agent_id,
                        exc,
                        working_payload,
                    )
                    continue

                symbol = intent.symbol
                side = intent.side
                requested_qty = float(intent.qty)
                limit_price = float(intent.limit) if intent.limit is not None else None
                order_type: OrderType = (intent.order_type or ("LMT" if limit_price is not None else "MKT"))  # type: ignore[assignment]
                tif: Optional[TimeInForce] = intent.time_in_force  # type: ignore[assignment]

                price = float(price_lookup.get(symbol, 0.0) or 0.0)
                if price <= 0.0:
                    self._log_drop(symbol, "missing price", {"side": side, "qty": requested_qty})
                    continue

                capped_qty = self._apply_risk_limits(
                    side=side,
                    requested_qty=requested_qty,
                    price=price,
                )
                if capped_qty <= 0:
                    self._log_drop(symbol, "risk limits", {"side": side, "qty": requested_qty})
                    continue

                meta: Dict[str, Any] = {}
                if condition_meta:
                    meta["condition_context"] = condition_meta
                if intent.notes:
                    meta["notes"] = intent.notes
                if "contingency" in expanded:
                    meta["contingency"] = expanded["contingency"]
                if "route" in expanded:
                    meta["route"] = expanded["route"]
                if "tags" in expanded:
                    meta["tags"] = expanded["tags"]
                if not meta:
                    meta = None  # type: ignore[assignment]

                orders.append(
                    Order(
                        agent_id=self.state.agent_id,
                        side=side,  # type: ignore[arg-type]
                        qty=capped_qty,
                        price_limit=limit_price,
                        symbol=symbol,
                        order_type=order_type,
                        time_in_force=tif,
                        stage=intent.stage,
                        condition=intent.condition or condition_label,
                        trigger=intent.trigger,
                        meta=meta,
                    )
                )
        return orders

    # --- Internal helpers ----------------------------------------------------
    def _log_drop(self, symbol: str, reason: str, context: Dict[str, Any]) -> None:
        _LOGGER.info(
            "LLMAgent %s dropped intent for %s: %s | %s",
            self.state.agent_id,
            symbol,
            reason,
            context,
        )

    def _apply_risk_limits(self, side: str, requested_qty: float, price: float) -> float:
        """
        Enforce coarse position and notional limits, returning a possibly-reduced
        quantity. Returns 0 if the order would breach limits entirely.
        """
        if price <= 0.0:
            return 0.0

        qty = max(0.0, float(requested_qty))

        # Position guard (symmetric long/short).
        max_position = self.risk_limits.get("max_position", float("inf"))
        if max_position < float("inf"):
            current = float(self.state.qty)
            room = self._position_room(side=side, current=current, limit=max_position)
            qty = min(qty, room)

        if qty <= 0.0:
            return 0.0

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
    def _expand_order_payload(raw_intent: Any) -> List[Dict[str, Any]]:
        if not isinstance(raw_intent, Mapping):
            return []
        base = dict(raw_intent)
        stages = base.pop("stages", None) or base.pop("legs", None)
        if not stages:
            return [base]

        expanded: List[Dict[str, Any]] = []
        for idx, stage in enumerate(stages or [], start=1):
            stage_payload: Dict[str, Any] = dict(base)
            if isinstance(stage, Mapping):
                stage_payload.update(stage)
            else:
                stage_payload["notes"] = stage
            label = stage_payload.get("stage") or stage_payload.get("label")
            stage_payload["stage"] = str(label).strip() if label else f"stage_{idx}"
            expanded.extend(LLMAgent._expand_order_payload(stage_payload))
        return expanded

    @staticmethod
    def _normalize_condition(raw_condition: Any) -> tuple[Optional[str], Optional[Dict[str, Any]]]:
        if raw_condition is None:
            return None, None
        if isinstance(raw_condition, str):
            cleaned = raw_condition.strip()
            return cleaned or None, None
        if isinstance(raw_condition, Mapping):
            label = raw_condition.get("label") or raw_condition.get("type")
            label_str = str(label).strip() if label else None
            return label_str or json.dumps(raw_condition, sort_keys=True), dict(raw_condition)
        if isinstance(raw_condition, list):
            label_str = "; ".join(str(item) for item in raw_condition if item is not None).strip()
            return label_str or None, {"clauses": raw_condition}
        return str(raw_condition), {"raw": raw_condition}

    @staticmethod
    def _position_room(side: str, current: float, limit: float) -> float:
        """How many additional units can we trade without exceeding limit."""
        if limit == float("inf"):
            return float("inf")
        if side == "BUY":
            return max(0.0, limit - current)
        if side == "SELL":
            return max(0.0, limit + current)
        raise ValueError(f"Unknown side: {side}")

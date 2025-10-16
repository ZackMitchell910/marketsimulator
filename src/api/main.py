from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import json
import os
import random
import threading
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from email.utils import format_datetime, parsedate_to_datetime
from pathlib import Path
from typing import Any, Deque, Dict, List, Mapping, MutableMapping, Optional, Union

from fastapi import (
    Body,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.agents.llm import LLMAgent
from src.config import env_loader  # noqa: F401 - ensure .env loading side effect
from src.sim.scenario_service import ScenarioService
from src.store.event_store import EventStore


class ScenarioRequest(BaseModel):
    text: str
    steps: int = Field(default=20, ge=1, le=500)

    def sanitized_steps(self) -> int:
        return max(5, min(int(self.steps), 120))


class IngestResponse(BaseModel):
    status: str
    buffer_size: int


app = FastAPI(title="MarketTwin API", version="0.5.0")


_SCENARIO_AGENTS: List[LLMAgent] = [
    LLMAgent(
        agent_id="persona-fund",
        persona={
            "name": "Institutional Fund",
            "description": "Multi-strategy macro fund balancing cross-asset exposures.",
            "mandate": "Deploy capital around macro catalysts while respecting firm-wide VaR limits.",
            "style": "macro-arb",
            "horizon": "swing",
            "risk_profile": {"max_drawdown": "8%", "target_vol": "12%", "gross_limit": "$5MM"},
            "playbook": [
                "Stage into positions with limit + stop-limit ladders around key levels",
                "Pair core exposure with conditional hedges to preserve VaR budget",
            ],
            "guidelines": [
                "Reference exposure in delta notional and include protection logic for every build",
                "Summarise trade thesis and catalysts in less than 40 words",
            ],
            "order_templates": [
                {
                    "label": "Scale-in with protective stop",
                    "comment": "Core ladder plus guardrail",
                    "stages": [
                        {"stage": "initial", "sizing": "40%", "order_type": "LMT", "offset": "-0.20%"},
                        {"stage": "momentum_add", "sizing": "35%", "order_type": "STOP_LIMIT", "trigger_offset": "+0.45%", "limit_offset": "+0.55%"},
                        {"stage": "trim", "sizing": "25%", "order_type": "LMT", "offset": "+0.90%", "side": "opposite"},
                    ],
                    "condition": "Attach STOP 0.8% beyond baseline and pair with target limit.",
                },
                {
                    "label": "Overnight hedge wrapper",
                    "stages": [
                        {"stage": "hedge_entry", "side": "opposite", "order_type": "STOP", "trigger_offset": "-0.60%"},
                    ],
                    "condition": "Deploy when catalyst carry risks gap-through losses.",
                },
            ],
        },
        risk_limits={"max_position": 10_000, "max_order_notional": 2_000_000, "max_notional": 5_000_000},
    ),
    LLMAgent(
        agent_id="persona-retail",
        persona={
            "name": "Retail Momentum",
            "description": "High-energy retail momentum chaser favouring breakout structures.",
            "style": "momentum",
            "horizon": "intraday",
            "risk_profile": {"max_drawdown": "12%", "position_size": "2k shares"},
            "playbook": [
                "Enter on breakout confirmation and trim quickly into strength",
                "Use bracket orders (stop + target) to automate exits",
            ],
            "guidelines": [
                "Keep commentary concise and actionable",
                "Always include stop and target per idea",
            ],
            "order_templates": [
                {
                    "label": "Bracket breakout",
                    "stages": [
                        {"stage": "entry", "order_type": "STOP_LIMIT", "trigger_offset": "+0.25%", "limit_offset": "+0.30%", "sizing": "60%"},
                        {"stage": "reload", "order_type": "STOP_LIMIT", "trigger_offset": "+0.60%", "limit_offset": "+0.65%", "sizing": "40%"},
                    ],
                    "condition": "Attach STOP -0.35% and target +1.1%.",
                }
            ],
        },
        risk_limits={"max_position": 2_000, "max_order_notional": 250_000, "max_notional": 500_000},
    ),
    LLMAgent(
        agent_id="persona-vol",
        persona={
            "name": "Vol Overlay Desk",
            "description": "Options overlay strategist managing convexity hedges.",
            "mandate": "Balance delta exposure with optionality around catalysts.",
            "style": "vol-targeting",
            "horizon": "swing",
            "risk_profile": {"vega_limit": "$750k", "gamma_limit": "$250k"},
            "playbook": [
                "Pair delta hedges with conditional spreads for convexity",
                "Stage into structures via conditional orders",
            ],
            "guidelines": [
                "Quote exposure in delta/vega terms",
                "Attach stops to hedge legs",
            ],
            "order_templates": [
                {
                    "label": "Delta hedge ladder",
                    "stages": [
                        {"stage": "hedge_entry", "order_type": "LMT", "sizing": "50%", "offset": "-0.15%"},
                        {"stage": "hedge_add", "order_type": "STOP_LIMIT", "trigger_offset": "+0.35%", "limit_offset": "+0.40%", "sizing": "30%"},
                        {"stage": "take_profit", "side": "opposite", "order_type": "LMT", "offset": "+0.70%", "sizing": "20%"},
                    ],
                    "condition": "Pair with STOP 0.5% through entry.",
                }
            ],
        },
        risk_limits={"max_position": 6_000, "max_order_notional": 1_500_000, "max_notional": 3_500_000},
    ),
]

_SCENARIO_SERVICE = ScenarioService(agents=_SCENARIO_AGENTS, seed=1337)

# --- Ring buffer for pushed events/fills/snapshots (single-process scope) ---
_RECENT: Deque[Dict[str, Any]] = deque(maxlen=500)

# --- Event streaming state ---------------------------------------------------
_EVENT_STORES: Dict[str, EventStore] = {}
_EVENT_STORES_LOCK = threading.Lock()
_DEMO_RUN_ID = "demo"
_DEMO_TASK: Optional[asyncio.Task] = None

# --- Scenario rate limiting --------------------------------------------------
_SCENARIO_RATE_MAX = int(os.getenv("MARKETTWIN_SCENARIO_RATE_MAX", "30"))
_SCENARIO_RATE_WINDOW = timedelta(seconds=int(os.getenv("MARKETTWIN_SCENARIO_RATE_WINDOW", "60")))
_SCENARIO_BUCKETS: MutableMapping[str, Deque[datetime]] = defaultdict(deque)

# --- Dashboard assets ---
DASH_DIR = (Path(__file__).resolve().parent.parent / "dashboard").resolve()
if DASH_DIR.exists():
    app.mount("/dashboard", StaticFiles(directory=str(DASH_DIR), html=True), name="dashboard")
else:
    print(f"[WARN] Dashboard directory not found: {DASH_DIR}")


# --- Ingest authentication & rate limiting ---------------------------------
_INGEST_API_KEY = os.getenv("MARKETTWIN_INGEST_API_KEY")
_RATE_LIMIT_MAX = int(os.getenv("MARKETSIM_INGEST_RATE_MAX", "120"))
_RATE_LIMIT_WINDOW = timedelta(seconds=int(os.getenv("MARKETSIM_INGEST_RATE_WINDOW", "60")))
_RATE_BUCKETS: MutableMapping[str, Deque[datetime]] = defaultdict(deque)


def _utc_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def _serialize_timestamp(ts: Any) -> str:
    if hasattr(ts, "to_pydatetime"):
        dt = ts.to_pydatetime()  # pandas.Timestamp -> datetime
    elif isinstance(ts, datetime):
        dt = ts
    else:
        dt = datetime.fromisoformat(str(ts))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")


def _enforce_rate_limit(bucket_id: str) -> None:
    now = datetime.now(timezone.utc)
    window = _RATE_LIMIT_WINDOW
    deque_ref = _RATE_BUCKETS[bucket_id]
    while deque_ref and now - deque_ref[0] > window:
        deque_ref.popleft()
    if len(deque_ref) >= _RATE_LIMIT_MAX:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Ingest rate limit exceeded",
        )
    deque_ref.append(now)


def _enforce_scenario_rate_limit(bucket_id: str) -> None:
    now = datetime.now(timezone.utc)
    window = _SCENARIO_RATE_WINDOW
    deque_ref = _SCENARIO_BUCKETS[bucket_id]
    while deque_ref and now - deque_ref[0] > window:
        deque_ref.popleft()
    if len(deque_ref) >= _SCENARIO_RATE_MAX:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Scenario rate limit exceeded",
        )
    deque_ref.append(now)


def _get_event_store(run_id: str) -> EventStore:
    key = run_id or "default"
    with _EVENT_STORES_LOCK:
        store = _EVENT_STORES.get(key)
        if store is None:
            store = EventStore()
            _EVENT_STORES[key] = store
        return store


async def publish_event(run_id: str, event: Dict[str, Any]) -> None:
    await _get_event_store(run_id).append(event)


async def verify_ingest_headers(
    request: Request,
    x_api_key: Optional[str] = Header(default=None, alias="x-api-key"),
) -> str:
    client_host = request.client.host if request.client else "unknown"
    bucket_id = client_host

    if not _INGEST_API_KEY:
        _enforce_rate_limit(bucket_id)
        await request.body()
        return "auth-disabled"

    if not x_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing API key")

    if not hmac.compare_digest(x_api_key, _INGEST_API_KEY):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")

    bucket_id = f"{x_api_key}:{client_host}"
    _enforce_rate_limit(bucket_id)
    await request.body()
    return x_api_key


@app.get("/")
def root_redirect() -> RedirectResponse:
    """Redirect root -> dashboard."""
    return RedirectResponse(url="/dashboard/")


@app.get("/health")
def health() -> Dict[str, bool]:
    return {"ok": True}


@app.post("/ingest", response_model=IngestResponse, status_code=status.HTTP_202_ACCEPTED)
async def ingest(
    _request: Request,
    payload: Union[Dict[str, Any], List[Dict[str, Any]]] = Body(...),
    _: str = Depends(verify_ingest_headers),
) -> IngestResponse:
    """
    Realtime process posts snapshots/fills here.
    Stored in ring buffer for dashboard/recent endpoint.
    """
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                _RECENT.append(item)
    elif isinstance(payload, dict):
        _RECENT.append(payload)
    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Payload must be dict or list[dict]")

    return IngestResponse(status="ok", buffer_size=len(_RECENT))


@app.get("/recent", response_model=List[Dict[str, Any]])
def recent(n: int = 50) -> List[Dict[str, Any]]:
    """Last N pushed events."""
    if not _RECENT:
        return JSONResponse(content=[], status_code=status.HTTP_204_NO_CONTENT)
    n = max(1, min(int(n), _RECENT.maxlen or 500))
    return list(_RECENT)[-n:]


@app.get("/events")
async def stream_events(run_id: str = _DEMO_RUN_ID, request: Request = None) -> StreamingResponse:
    """Server-Sent Events stream for realtime ticks/orders/trades."""
    store = _get_event_store(run_id)
    heartbeat_interval = 15.0

    async def event_stream():
        for snapshot in store.tail(50):
            yield f"data: {json.dumps(snapshot)}\n\n"

        subscriber = store.subscribe()
        try:
            while True:
                if request is not None and await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(subscriber.__anext__(), timeout=heartbeat_interval)
                    yield f"data: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                except StopAsyncIteration:
                    break
                except asyncio.CancelledError:
                    break
        finally:
            await subscriber.aclose()

    headers = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
    return StreamingResponse(event_stream(), media_type="text/event-stream", headers=headers)


@app.get("/metrics", response_model=Dict[str, Any])
def get_metrics(request: Request, response: Response) -> Union[Dict[str, Any], Response]:
    """Read newest metrics.json from runs/ with conditional caching."""
    runs = Path("runs")
    newest: Optional[Path] = None
    if runs.exists():
        for candidate in runs.rglob("metrics.json"):
            if (newest is None) or (candidate.stat().st_mtime > newest.stat().st_mtime):
                newest = candidate
    if not newest:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No metrics.json found")

    try:
        raw = newest.read_text(encoding="utf-8")
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Failed to read metrics: {exc}") from exc

    etag = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    last_modified = datetime.fromtimestamp(newest.stat().st_mtime, tz=timezone.utc)

    if_none_match = request.headers.get("if-none-match")
    if if_none_match and if_none_match == etag:
        return Response(status_code=status.HTTP_304_NOT_MODIFIED)

    if_modified_since = request.headers.get("if-modified-since")
    if if_modified_since:
        try:
            since = parsedate_to_datetime(if_modified_since)
            if since.tzinfo is None:
                since = since.replace(tzinfo=timezone.utc)
            else:
                since = since.astimezone(timezone.utc)
            if last_modified <= since:
                return Response(status_code=status.HTTP_304_NOT_MODIFIED)
        except (TypeError, ValueError):
            pass

    response.headers["ETag"] = etag
    response.headers["Last-Modified"] = format_datetime(last_modified)
    response.headers["Cache-Control"] = "public, max-age=30"

    return json.loads(raw)


@app.post("/scenario")
def run_scenario(req: ScenarioRequest, request: Request) -> Dict[str, Any]:
    """Convert free-text scenarios into projected market impacts."""
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Scenario text is required")

    client_host = request.client.host if request.client else "unknown"
    _enforce_scenario_rate_limit(client_host)

    impacts = _SCENARIO_SERVICE.run(text, steps=req.sanitized_steps())
    response_payload: List[Dict[str, Any]] = []
    for impact in impacts:
        projection = [
            {
                "timestamp": _serialize_timestamp(row.Index),
                "open": float(row.open),
                "high": float(row.high),
                "low": float(row.low),
                "close": float(row.close),
                "volume": float(row.volume),
            }
            for row in impact.projection.itertuples(index=True)
        ]
        orders = [
            {
                "agent_id": order.agent_id,
                "symbol": order.symbol or impact.ticker,
                "side": order.side,
                "qty": float(order.qty),
                "price_limit": float(order.price_limit) if order.price_limit is not None else None,
                "order_type": order.order_type,
                "time_in_force": order.time_in_force,
            }
            for order in impact.orders
        ]
        response_payload.append(
            {
                "ticker": impact.ticker,
                "score": float(impact.score),
                "baseline_price": float(impact.baseline_price),
                "projected_price": float(impact.projected_price),
                "current_price": float(impact.current_price),
                "orders": orders,
                "projection": projection,
            }
        )

    return {
        "scenario": text,
        "generated_at": _utc_iso(datetime.now(timezone.utc)),
        "impacts": response_payload,
    }


@app.get("/dashboard-index")
def dashboard_index_fallback():
    """Plain fallback index if dashboard build missing."""
    if not DASH_DIR.exists():
        return JSONResponse(
            {
                "info": "Dashboard assets not found. Put index.html under src/dashboard/",
                "expected_path": str(DASH_DIR),
            }
        )
    index_html = DASH_DIR / "index.html"
    if index_html.exists():
        return FileResponse(str(index_html))
    return JSONResponse({"detail": f"index.html not found in {DASH_DIR}"}, status_code=status.HTTP_404_NOT_FOUND)


async def _demo_event_publisher() -> None:
    run_id = _DEMO_RUN_ID
    symbols = ["SPY", "QQQ", "DIA"]
    prices = {symbol: 100.0 + idx * 2 for idx, symbol in enumerate(symbols)}
    seq = 0
    try:
        while True:
            event_type = random.choice(["tick", "order", "trade", "position"])
            symbol = random.choice(symbols)
            timestamp = _utc_iso(datetime.now(timezone.utc))
            base_event: Dict[str, Any] = {
                "run_id": run_id,
                "seq": seq,
                "type": event_type,
                "symbol": symbol,
                "timestamp": timestamp,
            }

            if event_type == "tick":
                prices[symbol] += random.uniform(-0.5, 0.5)
                event = {**base_event, "price": round(prices[symbol], 2)}
            elif event_type == "order":
                event = {
                    **base_event,
                    "side": random.choice(["BUY", "SELL"]),
                    "qty": round(random.uniform(10, 150), 2),
                    "limit": round(prices[symbol] + random.uniform(-1.5, 1.5), 2),
                }
            elif event_type == "trade":
                event = {
                    **base_event,
                    "qty": round(random.uniform(5, 120), 2),
                    "price": round(prices[symbol] + random.uniform(-0.75, 0.75), 2),
                    "agent_id": random.choice(["persona-fund", "persona-retail"]),
                }
            else:
                event = {
                    **base_event,
                    "qty": round(random.uniform(-200, 200), 2),
                    "pnl": round(random.uniform(-750, 750), 2),
                }

            await publish_event(run_id, event)
            seq += 1
            await asyncio.sleep(3)
    except asyncio.CancelledError:
        pass


@app.on_event("startup")
async def _start_demo_stream() -> None:
    global _DEMO_TASK
    if _DEMO_TASK is None:
        _DEMO_TASK = asyncio.create_task(_demo_event_publisher())


@app.on_event("shutdown")
async def _stop_demo_stream() -> None:
    global _DEMO_TASK
    if _DEMO_TASK:
        _DEMO_TASK.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await _DEMO_TASK
        _DEMO_TASK = None


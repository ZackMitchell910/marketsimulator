from __future__ import annotations

import json
from collections import deque
from datetime import datetime
from pathlib import Path
from typing import Any, Deque, Dict, List
import sys

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

ROOT_PATH = Path(__file__).resolve().parents[2]
if str(ROOT_PATH) not in sys.path:
    sys.path.append(str(ROOT_PATH))

from src.agents.llm import LLMAgent
from src.sim.scenario_service import ScenarioService

app = FastAPI(title="MarketTwin API", version="0.4.0")


class ScenarioRequest(BaseModel):
    text: str
    steps: int = 20

    def sanitized_steps(self) -> int:
        return max(5, min(int(self.steps), 120))


_SCENARIO_AGENTS: List[LLMAgent] = [
    LLMAgent(
        agent_id="persona-fund",
        persona={"name": "Institutional Fund", "style": "macro-arb", "horizon": "swing"},
        risk_limits={"max_position": 10_000, "max_order_notional": 2_000_000, "max_notional": 5_000_000},
    ),
    LLMAgent(
        agent_id="persona-retail",
        persona={"name": "Retail Momentum", "style": "intraday", "sentiment": "fast-twitch"},
        risk_limits={"max_position": 2_000, "max_order_notional": 250_000, "max_notional": 500_000},
    ),
]

_SCENARIO_SERVICE = ScenarioService(agents=_SCENARIO_AGENTS, seed=1337)

# --- Ring buffer for pushed events/fills/snapshots ---
_RECENT: Deque[Dict[str, Any]] = deque(maxlen=500)

# --- Dashboard assets ---
DASH_DIR = (Path(__file__).resolve().parent.parent / "dashboard").resolve()
if DASH_DIR.exists():
    app.mount("/dashboard", StaticFiles(directory=str(DASH_DIR), html=True), name="dashboard")
else:
    print(f"[WARN] Dashboard directory not found: {DASH_DIR}")


@app.get("/")
def root_redirect():
    """Redirect root -> dashboard"""
    return RedirectResponse(url="/dashboard/")


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/ingest")
def ingest(payload: Dict[str, Any] = Body(...)):
    """
    Realtime process posts snapshots/fills here.
    Stored in ring buffer for dashboard/recent endpoint.
    """
    _RECENT.append(payload)
    return {"status": "ok", "buffer_size": len(_RECENT)}


@app.get("/recent")
def recent(n: int = 50):
    """Last N pushed events"""
    if not _RECENT:
        raise HTTPException(status_code=404, detail="No recent events")
    n = max(1, min(int(n), 500))
    return list(_RECENT)[-n:]


@app.get("/metrics")
def get_metrics():
    """Read newest metrics.json from runs/"""
    runs = Path("runs")
    newest: Path | None = None
    if runs.exists():
        for candidate in runs.rglob("metrics.json"):
            if (newest is None) or (candidate.stat().st_mtime > newest.stat().st_mtime):
                newest = candidate
    if not newest:
        raise HTTPException(status_code=404, detail="No metrics.json found")
    try:
        return json.loads(newest.read_text(encoding="utf-8"))
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail=f"Failed to read metrics: {exc}") from exc


@app.post("/scenario")
def run_scenario(req: ScenarioRequest):
    """Convert free-text scenarios into projected market impacts."""
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Scenario text is required")

    impacts = _SCENARIO_SERVICE.run(text, steps=req.sanitized_steps())
    response_payload = []
    for impact in impacts:
        projection = [
            {
                "timestamp": ts.isoformat(),
                "open": float(row["open"]),
                "high": float(row["high"]),
                "low": float(row["low"]),
                "close": float(row["close"]),
                "volume": float(row["volume"]),
            }
            for ts, row in impact.projection.iterrows()
        ]
        orders = [
            {
                "agent_id": order.agent_id,
                "side": order.side,
                "qty": float(order.qty),
                "price_limit": float(order.price_limit) if order.price_limit is not None else None,
            }
            for order in impact.orders
        ]
        response_payload.append(
            {
                "ticker": impact.ticker,
                "score": float(impact.score),
                "orders": orders,
                "projection": projection,
            }
        )

    return {
        "scenario": text,
        "generated_at": datetime.utcnow().isoformat(),
        "impacts": response_payload,
    }


@app.get("/dashboard-index")
def dashboard_index_fallback():
    """Plain fallback index if dashboard build missing"""
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
    return JSONResponse({"detail": f"index.html not found in {DASH_DIR}"}, status_code=404)

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse

router = APIRouter()


@router.get("/ui/scenario", response_class=HTMLResponse)
async def scenario_ui():
    here = Path(__file__).resolve()
    template = here.parent.parent / "templates" / "scenario.html"
    if not template.exists():
        return HTMLResponse("<h1>Scenario UI missing</h1>", status_code=500)
    return FileResponse(template)

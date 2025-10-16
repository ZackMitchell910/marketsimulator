from __future__ import annotations

"""
Compatibility wrapper so `uvicorn dashboard.app:app --app-dir src` keeps working.
We simply re-export the FastAPI instance defined in `src/api/main.py`.
"""

from src.api.main import app  # noqa: F401


__all__ = ["app"]

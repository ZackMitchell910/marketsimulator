from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from dotenv import find_dotenv, load_dotenv


@lru_cache(maxsize=1)
def load_env(dotenv_path: Optional[str] = None, override: bool = False) -> bool:
    """
    Load environment variables from a .env file if present.

    Priority:
      1. Explicit ``dotenv_path`` argument.
      2. python-dotenv ``find_dotenv`` using the current working directory.
      3. Project root two levels above this file.

    Returns True if a file was loaded, otherwise False.
    """
    if dotenv_path:
        return load_dotenv(dotenv_path, override=override)

    discovered = find_dotenv(usecwd=True)
    if discovered:
        return load_dotenv(discovered, override=override)

    if os.getenv("MARKETTWIN_DISABLE_PROJECT_DOTENV") == "1":
        return False

    project_root = Path(__file__).resolve().parents[2]
    candidate = project_root / ".env"
    if candidate.exists():
        return load_dotenv(candidate, override=override)
    return False


# Load on import so API entry points pick up .env automatically.
load_env()

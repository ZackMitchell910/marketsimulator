# src/data/utils.py
from __future__ import annotations
import time, logging
from typing import Callable, TypeVar, Optional

T = TypeVar("T")

def safe_fetch(fn: Callable[[], T], *, retries: int = 3, backoff: float = 1.6) -> Optional[T]:
    for i in range(retries):
        try:
            data = fn()
            if data is None:
                raise ValueError("empty response")
            return data
        except Exception as e:
            logging.warning("safe_fetch fail %d/%d: %s", i+1, retries, e)
            if i < retries - 1:
                time.sleep(backoff ** i)
    logging.error("safe_fetch: permanent failure")
    return None

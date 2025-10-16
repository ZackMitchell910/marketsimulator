from __future__ import annotations

import json
import os
import time
from functools import lru_cache
from typing import List, Optional

import requests

POLYGON_NEWS_URL = "https://api.polygon.io/v2/reference/news"
CACHE_TTL = 300  # seconds


class PolygonNewsError(RuntimeError):
    pass


@lru_cache(maxsize=128)
def _cached_fetch(ticker: str, limit: int) -> tuple[float, List[dict]]:
    api_key = os.getenv("POLYGON_API_KEY") or os.getenv("PT_POLYGON_KEY")
    if not api_key:
        raise PolygonNewsError("Polygon API key not configured")
    params = {
        "ticker": ticker.upper(),
        "limit": limit,
        "order": "desc",
        "sort": "published_utc",
        "apiKey": api_key,
    }
    resp = requests.get(POLYGON_NEWS_URL, params=params, timeout=5)
    if resp.status_code == 403:
        raise PolygonNewsError("Polygon API access forbidden - check plan or key.")
    resp.raise_for_status()
    payload = resp.json()
    results = payload.get("results", [])
    return time.time(), results


def fetch_recent_news(ticker: str, limit: int = 3) -> List[dict]:
    """
    Retrieve recent Polygon news for a ticker. Falls back to cached data when TTL not expired.
    """
    cache_key = (ticker.upper(), min(max(limit, 1), 10))
    try:
        ts, records = _cached_fetch(*cache_key)
        if time.time() - ts > CACHE_TTL:
            _cached_fetch.cache_clear()
            ts, records = _cached_fetch(*cache_key)
        formatted = []
        for item in records[: cache_key[1]]:
            formatted.append(
                {
                    "title": item.get("title"),
                    "url": item.get("article_url"),
                    "source": item.get("source"),
                    "published": item.get("published_utc"),
                    "tickers": item.get("tickers") or [],
                }
            )
        return formatted
    except PolygonNewsError:
        return []
    except (requests.RequestException, json.JSONDecodeError):
        return []

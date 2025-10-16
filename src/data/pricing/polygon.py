from __future__ import annotations

import json
import os
from functools import lru_cache
from typing import Optional

import requests

_POLYGON_KEY_ENV_VARS = (
    'POLYGON_API_KEY',
    'PT_POLYGON_KEY',
)

_BASE_URL = 'https://api.polygon.io'


def _get_api_key() -> Optional[str]:
    for var in _POLYGON_KEY_ENV_VARS:
        value = os.getenv(var)
        if value:
            return value
    return None


@lru_cache(maxsize=128)
def get_last_price(symbol: str) -> Optional[float]:
    api_key = _get_api_key()
    if not api_key or not symbol:
        return None
    symbol = symbol.upper()
    endpoint = f'/v2/last/trade/{symbol}'
    try:
        response = requests.get(
            _BASE_URL + endpoint,
            params={'apiKey': api_key},
            timeout=5,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, json.JSONDecodeError):
        return None

    try:
        price = float(payload['results']['p'])
    except (KeyError, TypeError, ValueError):
        return None
    return price



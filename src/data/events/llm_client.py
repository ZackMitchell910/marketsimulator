from __future__ import annotations

import json
import logging
import os
from functools import lru_cache
from typing import Callable, Iterable, List, Optional, Sequence, Tuple

import requests

try:
    import openai  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    openai = None  # type: ignore

from . import vector_store

LOGGER = logging.getLogger(__name__)

_OPENAI_KEY_ENV_VARS: Sequence[str] = (
    "MARKETTWIN_OPENAI_API_KEY",
    "OPENAI_API_KEY",
)
_OPENAI_MODEL_ENV = "MARKETTWIN_SCENARIO_MODEL"
_OPENAI_DEFAULT_MODEL = "gpt-3.5-turbo"

_GROK_KEY_ENV_VARS: Sequence[str] = (
    "MARKETTWIN_GROK_API_KEY",
    "GROK_API_KEY",
    "XAI_API_KEY",
)
_GROK_MODEL_ENV_VARS: Sequence[str] = (
    "XAI_MODEL",
    "MARKETTWIN_GROK_MODEL",
)
_GROK_DEFAULT_MODEL = "grok-beta"
_GROK_ENDPOINT_ENV = "MARKETTWIN_GROK_ENDPOINT"
_GROK_DEFAULT_ENDPOINT = "https://api.x.ai/v1/chat/completions"


def score_impacts(headline: str, top_n: int = 3, context: Optional[str] = None) -> List[Tuple[str, float]]:
    """
    Ask an upstream LLM to rank the top impacted tickers for a given headline.
    Returns an empty list if no configuration is present or the call fails.
    """
    if not headline or top_n <= 0:
        return []

    cached = vector_store.get_cached_response(headline)
    if cached:
        combined = cached.get("combined") or []
        return [(item["symbol"], float(item["weight"])) for item in combined][:top_n]

    provider_name, provider = _choose_provider()
    if provider is None:
        return []

    retrieval_context = vector_store.build_retrieval_context(headline)
    combined_context = "\n\n".join(
        part for part in [retrieval_context, context] if part
    )

    try:
        raw = _cached_fetch(provider_name, headline.strip(), int(top_n), combined_context or "")
    except Exception as exc:  # pragma: no cover - safety net
        LOGGER.warning("Scenario LLM lookup failed: %s", exc)
        return []

    normalized = _normalize_impacts(raw, top_n=top_n)
    impacts = normalized["combined"]
    if not impacts:
        LOGGER.warning("Scenario LLM returned empty or malformed payload: %s", raw)
        return []

    vector_store.cache_response(
        headline=headline.strip(),
        summary=normalized["summary"],
        positive=normalized["positive"],
        negative=normalized["negative"],
        combined=impacts,
    )
    return impacts[:top_n]


@lru_cache(maxsize=128)
def _cached_fetch(provider_name: str, headline: str, top_n: int, context: str) -> str:
    _, provider = _choose_provider()
    if provider is None:
        raise RuntimeError("No LLM provider configured")
    return provider(headline, top_n, context or "")


def _choose_provider() -> Tuple[str, Callable[[str, int, str], str] | None]:
    if _get_grok_key():
        return "grok", _call_grok
    if openai is not None and _get_openai_key():
        return "openai", _call_openai
    return "none", None


def _get_openai_key() -> str | None:
    for var in _OPENAI_KEY_ENV_VARS:
        value = os.getenv(var)
        if value:
            return value
    return None


def _get_grok_key() -> str | None:
    for var in _GROK_KEY_ENV_VARS:
        value = os.getenv(var)
        if value:
            return value
    return None


def _get_grok_model(default: str = _GROK_DEFAULT_MODEL) -> str:
    for var in _GROK_MODEL_ENV_VARS:
        value = os.getenv(var)
        if value:
            return value
    return default


def _prompt_text(top_n: int) -> str:
    return (
        "You are MarketSimulator-X, an autonomous macro strategist. Given a scenario headline, "
        "determine the top impacted US-listed equities. Separate your answer into the three most "
        "positively shocked tickers and the three most negatively shocked tickers. Provide weights "
        "between 0 and 1 indicating magnitude (1 = extreme impact). Respond strictly as JSON:\n"
        '{\n  "summary": "short narrative",\n  "positive_impacts": [{"symbol": "IWM", "weight": 0.85}, ...],\n'
        '  "negative_impacts": [{"symbol": "TLT", "weight": 0.7}, ...]\n}\n'
        f"Each list may contain fewer than {top_n} items if warranted. Use ticker symbols only."
    )


def _augment_messages(headline: str, context: str) -> List[dict]:
    messages = [
        {"role": "user", "content": headline.strip()},
    ]
    if context:
        messages.insert(
            0,
            {
                "role": "system",
                "content": (
                    "Supplementary market context:\n"
                    f"{context.strip()}"
                ),
            },
        )
    return messages


def _call_openai(headline: str, top_n: int, context: str) -> str:
    if openai is None:
        raise RuntimeError("openai package not available")

    api_key = _get_openai_key()
    if not api_key:
        raise RuntimeError("OpenAI API key is not configured")

    openai.api_key = api_key  # type: ignore[attr-defined]
    model = os.getenv(_OPENAI_MODEL_ENV, _OPENAI_DEFAULT_MODEL)
    system_prompt = _prompt_text(top_n)

    completion = openai.ChatCompletion.create(  # type: ignore[attr-defined]
        model=model,
        temperature=0.1,
        messages=[{"role": "system", "content": system_prompt}] + _augment_messages(headline, context),
    )

    choice = completion["choices"][0]["message"]["content"]
    if not isinstance(choice, str):
        raise ValueError("Unexpected LLM response payload")
    return choice


def _call_grok(headline: str, top_n: int, context: str) -> str:
    api_key = _get_grok_key()
    if not api_key:
        raise RuntimeError("Grok API key is not configured")

    endpoint = os.getenv(_GROK_ENDPOINT_ENV, _GROK_DEFAULT_ENDPOINT)
    model = _get_grok_model()
    system_prompt = _prompt_text(top_n)

    payload = {
        "model": model,
        "temperature": 0.1,
        "messages": [
            {"role": "system", "content": system_prompt},
            *(
                [{"role": "system", "content": f"Supplementary market context:\n{context.strip()}"}]
                if context
                else []
            ),
            {"role": "user", "content": headline.strip()},
        ],
    }

    response = requests.post(
        endpoint,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()

    try:
        choice = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"Unexpected Grok response payload: {data}") from exc

    if not isinstance(choice, str):
        raise ValueError("Unexpected Grok response payload")
    return choice


def _normalize_impacts(raw: str | Sequence[dict] | dict, top_n: int) -> Dict[str, object]:
    data = _coerce_to_mapping(raw)
    if not data:
        return {"combined": [], "positive": [], "negative": [], "summary": None}

    summary = data.get("summary")
    positives: Iterable[dict] = data.get("positive_impacts") or []
    negatives: Iterable[dict] = data.get("negative_impacts") or []
    combined: List[Tuple[str, float]] = []
    positive_structured: List[Dict[str, float]] = []
    negative_structured: List[Dict[str, float]] = []
    seen = set()

    for item in positives:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol", "")).strip().upper()
        if not symbol or symbol in seen:
            continue
        weight_val = _coerce_weight(item.get("weight", item.get("score", 0.5)))
        combined.append((symbol, weight_val))
        positive_structured.append({"symbol": symbol, "weight": weight_val})
        seen.add(symbol)

    for item in negatives:
        if not isinstance(item, dict):
            continue
        symbol = str(item.get("symbol", "")).strip().upper()
        if not symbol or symbol in seen:
            continue
        weight_val = -_coerce_weight(item.get("weight", item.get("score", 0.5)))
        combined.append((symbol, weight_val))
        negative_structured.append({"symbol": symbol, "weight": weight_val})
        seen.add(symbol)

    combined.sort(key=lambda kv: abs(kv[1]), reverse=True)

    return {
        "summary": summary,
        "positive": positive_structured,
        "negative": negative_structured,
        "combined": combined[:top_n],
    }


def _coerce_weight(value: object) -> float:
    try:
        weight_val = float(value)
    except (TypeError, ValueError):
        weight_val = 0.5
    return max(0.0, min(weight_val, 1.0))


def _coerce_to_mapping(raw: str | Sequence[dict] | dict) -> dict | None:
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, (list, tuple)):
        return {"impacts": list(raw)}
    if isinstance(raw, str):
        text = raw.strip()
        if text.startswith("```"):
            text = _strip_code_fence(text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}")
            if start != -1 and end != -1 and end > start:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _strip_code_fence(text: str) -> str:
    if not text.startswith("```"):
        return text
    stripped = text.split("\n", 1)[-1]
    if stripped.endswith("```"):
        stripped = stripped[: stripped.rfind("```")]
    return stripped.strip()

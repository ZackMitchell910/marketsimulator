from __future__ import annotations

import json
import math
import os
import re
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


_STORE_PATH = Path(
    os.getenv(
        "MARKETTWIN_SCENARIO_STORE",
        Path(__file__).resolve().parent.parent / "scenarios" / "history.jsonl",
    )
)


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _to_vector(tokens: Iterable[str]) -> Dict[str, float]:
    counts = Counter(tokens)
    if not counts:
        return {}
    norm = math.sqrt(sum(v * v for v in counts.values())) or 1.0
    return {token: value / norm for token, value in counts.items()}


def _cosine_similarity(vec_a: Dict[str, float], vec_b: Dict[str, float]) -> float:
    if not vec_a or not vec_b:
        return 0.0
    if len(vec_a) > len(vec_b):
        vec_a, vec_b = vec_b, vec_a
    dot = sum(weight * vec_b.get(token, 0.0) for token, weight in vec_a.items())
    return float(dot)


@lru_cache(maxsize=1)
def _load_entries() -> List[Dict[str, object]]:
    entries: List[Dict[str, object]] = []
    if not _STORE_PATH.exists():
        return entries
    with _STORE_PATH.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            vector_pairs = raw.get("vector", [])
            raw["vector"] = {token: float(weight) for token, weight in vector_pairs}
            entries.append(raw)
    return entries


def _invalidate_cache() -> None:
    _load_entries.cache_clear()  # type: ignore[attr-defined]


def find_similar(headline: str, top_k: int = 3) -> List[Dict[str, object]]:
    tokens = _tokenize(headline)
    vector = _to_vector(tokens)
    if not vector:
        return []
    results: List[Dict[str, object]] = []
    for entry in _load_entries():
        similarity = _cosine_similarity(vector, entry.get("vector", {}))
        if similarity <= 0:
            continue
        results.append({"entry": entry, "similarity": similarity})
    results.sort(key=lambda item: item["similarity"], reverse=True)
    return results[:top_k]


def get_cached_response(headline: str, threshold: float = 0.92) -> Optional[Dict[str, object]]:
    matches = find_similar(headline, top_k=1)
    if not matches:
        return None
    top = matches[0]
    if top["similarity"] < threshold:
        return None
    entry = top["entry"]
    return {
        "summary": entry.get("summary"),
        "positive": entry.get("positive", []),
        "negative": entry.get("negative", []),
        "combined": entry.get("combined", []),
    }


def build_retrieval_context(headline: str, top_k: int = 3) -> str:
    matches = find_similar(headline, top_k=top_k)
    if not matches:
        return ""
    lines = ["Historical analogs:"]
    for item in matches:
        entry = item["entry"]
        lines.append(
            f"- {entry.get('headline')}: similarity {item['similarity']:.2f} · summary: {entry.get('summary', 'N/A')}"
        )
    return "\n".join(lines)


def cache_response(
    headline: str,
    summary: Optional[str],
    positive: List[Dict[str, object]],
    negative: List[Dict[str, object]],
    combined: List[Tuple[str, float]],
) -> None:
    vector = _to_vector(_tokenize(headline))
    entry = {
        "headline": headline,
        "summary": summary,
        "positive": positive,
        "negative": negative,
        "combined": [{"symbol": symbol, "weight": weight} for symbol, weight in combined],
        "vector": list(vector.items()),
    }
    _STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _STORE_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry) + "\n")
    _invalidate_cache()

from __future__ import annotations

import json
import math
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

DATA_PATH = Path(__file__).resolve().parents[3] / "data" / "market" / "event_analogs.json"

STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "at",
    "be",
    "but",
    "by",
    "for",
    "from",
    "in",
    "into",
    "is",
    "it",
    "of",
    "on",
    "or",
    "that",
    "the",
    "to",
    "with",
}


def _tokenize(text: str) -> List[str]:
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return [tok for tok in tokens if tok and tok not in STOP_WORDS]


def _load_dataset() -> List[Dict[str, object]]:
    if not DATA_PATH.exists():
        return []
    with DATA_PATH.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    records: List[Dict[str, object]] = []
    for entry in data:
        entry = dict(entry)
        content = " ".join(
            filter(
                None,
                [
                    entry.get("title"),
                    entry.get("summary"),
                    " ".join(entry.get("tags") or []),
                    entry.get("category"),
                ],
            )
        )
        entry["_tokens"] = _tokenize(content)
        records.append(entry)
    return records


@lru_cache(maxsize=1)
def load_index() -> List[Dict[str, object]]:
    return _load_dataset()


def _score_tokens(query_tokens: Sequence[str], doc_tokens: Sequence[str]) -> float:
    if not query_tokens or not doc_tokens:
        return 0.0
    query_set = set(query_tokens)
    doc_set = set(doc_tokens)
    overlap = query_set.intersection(doc_set)
    if not overlap:
        return 0.0
    overlap_score = len(overlap) / math.sqrt(len(query_set) * len(doc_set))
    frequency_bonus = sum(doc_tokens.count(tok) for tok in overlap) / (len(doc_tokens) or 1)
    return overlap_score + 0.2 * frequency_bonus


def match_analogs(
    scenario_text: str,
    tickers: Optional[Iterable[str]] = None,
    top_n: int = 3,
) -> Dict[str, List[Dict[str, object]]]:
    """
    Score historical analog events against the scenario narrative and optional ticker list.
    Returns a mapping ticker -> sorted list of analogs with similarity scores.
    """
    dataset = load_index()
    if not dataset:
        return {}

    query_tokens = _tokenize(scenario_text or "")
    if not query_tokens:
        return {}

    ticker_set = {t.upper() for t in tickers or [] if t}
    results: Dict[str, List[Tuple[float, Dict[str, object]]]] = {}

    for entry in dataset:
        entry_tokens = entry.get("_tokens") or []
        score = _score_tokens(query_tokens, entry_tokens)
        if score <= 0:
            continue
        ticker = str(entry.get("ticker", "")).upper()
        if ticker_set and ticker not in ticker_set:
            # allow small bleed through if tag overlap is substantial (>=0.75 score)
            if score < 0.75:
                continue
        enriched = {
            k: v
            for k, v in entry.items()
            if not k.startswith("_")
        }
        enriched["similarity"] = round(score, 3)
        results.setdefault(ticker, []).append((score, enriched))

    top_matches: Dict[str, List[Dict[str, object]]] = {}
    for ticker, matches in results.items():
        sorted_matches = sorted(matches, key=lambda kv: kv[0], reverse=True)[:top_n]
        top_matches[ticker] = [item for _, item in sorted_matches]
    return top_matches


def aggregate_metrics(analogs: Mapping[str, List[Mapping[str, object]]]) -> Dict[str, Dict[str, float]]:
    """
    Reduce analog collections into per-ticker metrics (avg drift/vol/skew/kurtosis).
    """
    aggregates: Dict[str, Dict[str, float]] = {}
    for ticker, items in analogs.items():
        if not items:
            continue
        def _collect(key: str) -> List[float]:
            vals = []
            for item in items:
                value = item.get(key)
                if isinstance(value, (int, float)):
                    vals.append(float(value))
            return vals

        drift_vals = _collect("drift")
        vol_vals = _collect("vol")
        skew_vals = _collect("skew")
        kurt_vals = _collect("kurtosis")

        aggregates[ticker] = {
            "drift_avg": sum(drift_vals) / len(drift_vals) if drift_vals else 0.0,
            "vol_avg": sum(vol_vals) / len(vol_vals) if vol_vals else 0.0,
            "skew_avg": sum(skew_vals) / len(skew_vals) if skew_vals else 0.0,
            "kurtosis_avg": sum(kurt_vals) / len(kurt_vals) if kurt_vals else 3.0,
            "sample_size": len(items),
        }
    return aggregates

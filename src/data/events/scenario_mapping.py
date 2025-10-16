from __future__ import annotations

import re
from typing import Dict, List, Tuple

# Basic keyword-to-ticker associations. This can be extended with richer NLP or
# pulled from a knowledge graph; for now we encode battle-tested heuristics that
# cover common geopolitical and macro themes.
KEYWORD_TICKER_MAP: Dict[str, List[Tuple[str, float]]] = {
    "war": [
        ("LMT", 1.0),  # Lockheed Martin
        ("RTX", 0.9),  # Raytheon
        ("NOC", 0.85),  # Northrop Grumman
    ],
    "mexico": [
        ("KSU", 0.6),  # Kansas City Southern (rail exposure)
        ("GM", 0.55),  # Auto supply chain ties
        ("CX", 0.5),  # Cemex
    ],
    "oil": [
        ("XOM", 0.8),
        ("CVX", 0.75),
        ("SLB", 0.65),
    ],
    "chip": [
        ("NVDA", 0.9),
        ("AMD", 0.85),
        ("TSM", 0.8),
    ],
    "currency": [
        ("FXE", 0.5),
        ("UUP", 0.5),
    ],
}


def extract_impact_candidates(text: str, top_n: int = 3) -> List[Tuple[str, float]]:
    """
    Very lightweight keyword matching to return plausible impacted tickers. The
    higher the floating weight, the stronger the association.
    """
    if not text:
        return []

    lowered = text.lower()
    hits: Dict[str, float] = {}
    matched_keywords = []

    for keyword, entries in KEYWORD_TICKER_MAP.items():
        if not re.search(rf"\b{re.escape(keyword)}\b", lowered):
            continue
        matched_keywords.append((keyword, entries))
        for ticker, weight in entries:
            hits[ticker] = max(hits.get(ticker, 0.0), weight)

    if not hits:
        return []

    ranked = sorted(hits.items(), key=lambda kv: kv[1], reverse=True)

    # Ensure at least one representative for each matched keyword when possible.
    selected: List[Tuple[str, float]] = []
    for _, entries in matched_keywords:
        best = max(entries, key=lambda item: item[1])
        if best[0] not in {ticker for ticker, _ in selected}:
            selected.append(best)
            if len(selected) >= top_n:
                break

    for ticker, weight in ranked:
        if ticker in {t for t, _ in selected}:
            continue
        selected.append((ticker, weight))
        if len(selected) >= top_n:
            break

    return selected[:top_n]

from __future__ import annotations

import logging
from typing import Dict, List, Tuple

from . import analog_index, context, llm_client

LOGGER = logging.getLogger(__name__)


def extract_impact_candidates(text: str, top_n: int = 3) -> List[Tuple[str, float]]:
    """Use XAI/Grok to derive the most impacted tickers, falling back to heuristics."""
    if not text:
        return []

    derived = context.derive_context(text, top_n=top_n * 2)
    prompt_context = derived["context_text"]

    llm_results = llm_client.score_impacts(text, top_n=top_n * 2, context=prompt_context)

    analog_matches = analog_index.match_analogs(text, [symbol for symbol, _ in derived["candidates"]], top_n=3)
    analog_scores: Dict[str, float] = {
        ticker: max(match.get("similarity", 0.0) for match in matches or [])
        for ticker, matches in analog_matches.items()
    }

    if llm_results:
        boosted: List[Tuple[str, float]] = []
        for symbol, score in llm_results:
            boost = analog_scores.get(symbol.upper(), 0.0)
            boosted.append((symbol, score + boost))
        boosted.sort(key=lambda kv: kv[1], reverse=True)
        return boosted[:top_n]

    fallback = derived["candidates"][:top_n]
    if analog_scores:
        adjusted: List[Tuple[str, float]] = []
        for symbol, score in fallback:
            adjusted.append((symbol, score + analog_scores.get(symbol.upper(), 0.0)))
        adjusted.sort(key=lambda kv: kv[1], reverse=True)
        return adjusted[:top_n]
    return fallback

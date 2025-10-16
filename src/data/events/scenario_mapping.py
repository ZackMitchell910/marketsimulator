from __future__ import annotations

import logging
from typing import List, Tuple

from . import context, llm_client

LOGGER = logging.getLogger(__name__)


def extract_impact_candidates(text: str, top_n: int = 3) -> List[Tuple[str, float]]:
    """Use XAI/Grok to derive the most impacted tickers, falling back to heuristics."""
    if not text:
        return []

    derived = context.derive_context(text, top_n=top_n * 2)
    prompt_context = derived["context_text"]

    llm_results = llm_client.score_impacts(text, top_n=top_n, context=prompt_context)
    if llm_results:
        return llm_results[:top_n]

    fallback = derived["candidates"][:top_n]
    return fallback

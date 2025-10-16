from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from typing import Dict, List, Tuple

KEYWORD_TICKER_MAP: Dict[str, List[Tuple[str, float]]] = {
    "rate": [("XLF", 0.6), ("KRE", 0.55), ("TLT", 0.5)],
    "rates": [("XLF", 0.62), ("KRE", 0.58), ("TLT", 0.55)],
    "inflation": [("GLD", 0.6), ("XLE", 0.55), ("TIP", 0.5)],
    "stimulus": [("XRT", 0.55), ("XLY", 0.52), ("IWM", 0.58)],
    "war": [("LMT", 0.9), ("RTX", 0.85), ("NOC", 0.8)],
    "mexico": [("KSU", 1.5), ("GM", 1.3), ("CX", 1.2)],
    "tax": [("IWM", 0.6), ("XLI", 0.55), ("RSP", 0.5)],
    "tariff": [("IYT", 0.55), ("XLI", 0.52)],
    "defense": [("LMT", 0.8), ("RTX", 0.75), ("NOC", 0.7)],
    "chip": [("NVDA", 0.9), ("AMD", 0.85), ("TSM", 0.8), ("SOXX", 0.7)],
    "semiconductor": [("NVDA", 0.9), ("AMD", 0.85), ("TSM", 0.8), ("SOXX", 0.7)],
    "ai": [("NVDA", 0.88), ("MSFT", 0.8), ("GOOGL", 0.75)],
    "energy": [("XLE", 0.65), ("XOM", 0.6), ("CVX", 0.58)],
    "oil": [("XOM", 0.7), ("CVX", 0.68), ("SLB", 0.6), ("XLE", 0.6)],
    "bank": [("JPM", 0.7), ("BAC", 0.65), ("XLF", 0.6)],
    "crypto": [("COIN", 0.65), ("MSTR", 0.6), ("BTC-USD", 0.55)],
    "automotive": [("TSLA", 0.75), ("GM", 0.6), ("F", 0.55)],
    "pharma": [("PFE", 0.6), ("MRNA", 0.58), ("JNJ", 0.55)],
    "biotech": [("XBI", 0.6), ("IBB", 0.58), ("MRNA", 0.55)],
    "retail": [("XRT", 0.62), ("AMZN", 0.6), ("WMT", 0.58)],
    "travel": [("DAL", 0.6), ("CCL", 0.55), ("AAL", 0.52)],
    "airline": [("JETS", 0.6), ("DAL", 0.58), ("UAL", 0.55)],
    "housing": [("XHB", 0.6), ("HD", 0.56), ("LOW", 0.54)],
    "metals": [("XME", 0.6), ("CLF", 0.55), ("AA", 0.53)],
    "industrial": [("CAT", 0.62), ("DE", 0.6), ("XLI", 0.58)],
    "manufacturing": [("XLI", 0.6), ("CAT", 0.58), ("IWM", 0.55)],
    "small-cap": [("IWM", 0.7), ("RSP", 0.65)],
}

TICKER_METADATA: Dict[str, Dict[str, str]] = {
    "NVDA": {"sector": "Information Technology", "industry": "Semiconductors", "beta": "1.70"},
    "AMD": {"sector": "Information Technology", "industry": "Semiconductors", "beta": "1.90"},
    "TSM": {"sector": "Information Technology", "industry": "Semiconductors", "beta": "1.15"},
    "SOXX": {"sector": "Information Technology", "industry": "Semiconductor ETF"},
    "SPY": {"sector": "Multi", "industry": "Broad Market ETF"},
    "QQQ": {"sector": "Information Technology", "industry": "Growth ETF"},
    "DIA": {"sector": "Multi", "industry": "Industrial Focus ETF"},
    "XLF": {"sector": "Financials", "industry": "Financial ETF"},
    "KRE": {"sector": "Financials", "industry": "Regional Banks"},
    "IWM": {"sector": "Multi", "industry": "Small Cap"},
    "CAT": {"sector": "Industrials", "industry": "Machinery"},
    "XLI": {"sector": "Industrials", "industry": "Industrial ETF"},
    "XRT": {"sector": "Consumer Discretionary", "industry": "Retail ETF"},
    "TSLA": {"sector": "Consumer Discretionary", "industry": "Automotive"},
    "XLE": {"sector": "Energy", "industry": "Energy ETF"},
    "XOM": {"sector": "Energy", "industry": "Oil & Gas"},
    "CVX": {"sector": "Energy", "industry": "Oil & Gas"},
    "LMT": {"sector": "Industrials", "industry": "Defense"},
    "RTX": {"sector": "Industrials", "industry": "Defense"},
    "NOC": {"sector": "Industrials", "industry": "Defense"},
    "KSU": {"sector": "Industrials", "industry": "Rail"},
    "GM": {"sector": "Consumer Discretionary", "industry": "Automotive"},
    "CX": {"sector": "Materials", "industry": "Cement"},
}

POSITIVE_TERMS = {
    "boost",
    "growth",
    "surge",
    "record",
    "accrete",
    "improve",
    "expand",
    "support",
    "stimulus",
    "cut",
    "increase",
    "beat",
}

NEGATIVE_TERMS = {
    "cutback",
    "slowdown",
    "slump",
    "fall",
    "drop",
    "miss",
    "decline",
    "recession",
    "layoff",
    "bankrupt",
    "default",
}

PHRASE_SENTIMENT = {
    "rate cut": 0.6,
    "cuts rates": 0.6,
    "cut rates": 0.6,
    "drops rates": 0.5,
    "rate hike": -0.6,
    "hikes rates": -0.6,
    "raise rates": -0.5,
}

PHRASE_TICKER_BOOST: Dict[str, List[Tuple[str, float]]] = {
    "rate cut": [("XLF", 0.9), ("IWM", 0.8), ("XLY", 0.75)],
    "cuts rates": [("XLF", 0.9), ("IWM", 0.8), ("XLY", 0.75)],
    "cut rates": [("XLF", 0.9), ("IWM", 0.8), ("XLY", 0.75)],
    "drops rates": [("XLF", 0.9), ("IWM", 0.78), ("XRT", 0.72)],
    "rate hike": [("TLT", 0.8), ("XLF", 0.72), ("KRE", 0.7)],
}


def derive_context(text: str, top_n: int = 5) -> Dict[str, object]:
    lowered = text.lower()
    keyword_hits = Counter()
    for keyword in KEYWORD_TICKER_MAP:
        if re.search(rf"\b{re.escape(keyword)}\b", lowered):
            keyword_hits[keyword] += 1

    ticker_scores: Dict[str, float] = defaultdict(float)
    for keyword, count in keyword_hits.items():
        for ticker, weight in KEYWORD_TICKER_MAP.get(keyword, []):
            ticker_scores[ticker] += weight * count

    for phrase, boosts in PHRASE_TICKER_BOOST.items():
        if phrase in lowered:
            for ticker, weight in boosts:
                ticker_scores[ticker] += weight

    sorted_tickers = sorted(ticker_scores.items(), key=lambda kv: kv[1], reverse=True)[:top_n]
    enriched = []
    for ticker, weight in sorted_tickers:
        meta = TICKER_METADATA.get(ticker, {})
        enriched.append(
            {
                "symbol": ticker,
                "weight": round(min(1.0, weight / (weight + 1.0)), 3),
                "sector": meta.get("sector"),
                "industry": meta.get("industry"),
                "beta": meta.get("beta"),
            }
        )

    ordered: List[dict] = []
    added = set()
    for keyword in keyword_hits:
        keyword_tickers = {t for t, _ in KEYWORD_TICKER_MAP.get(keyword, [])}
        for item in enriched:
            if item["symbol"] in keyword_tickers and item["symbol"] not in added:
                ordered.append(item)
                added.add(item["symbol"])
                break

    for item in enriched:
        if item["symbol"] not in added:
            ordered.append(item)

    ordered = ordered[:top_n]

    sentiment = estimate_sentiment(lowered)
    context_lines = [
        f"Sentiment score: {sentiment:+.2f}",
        f"Keyword hits: {', '.join(keyword_hits.elements()) or 'None'}",
    ]
    if enriched:
        for item in enriched:
            context_lines.append(
                f"{item['symbol']} | weight={item['weight']} | sector={item.get('sector') or 'NA'} | industry={item.get('industry') or 'NA'}"
            )

    return {
        "sentiment": sentiment,
        "candidates": [(item["symbol"], item["weight"]) for item in ordered],
        "context_text": "\n".join(context_lines),
    }


def estimate_sentiment(text: str) -> float:
    if not text:
        return 0.0
    pos = sum(text.count(term) for term in POSITIVE_TERMS)
    neg = sum(text.count(term) for term in NEGATIVE_TERMS)
    phrase_score = 0.0
    for phrase, value in PHRASE_SENTIMENT.items():
        if phrase in text:
            phrase_score += value
    score = pos - neg
    score += phrase_score * 3  # amplify phrase impact
    if score == 0:
        return 0.0
    scaled = math.tanh(score / 5.0)
    return scaled


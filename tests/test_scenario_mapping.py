from __future__ import annotations

import pytest

from src.data.events import context, llm_client, scenario_mapping, vector_store


def clear_llm_cache():
    llm_client._cached_fetch.cache_clear()  # type: ignore[attr-defined]


def stub_vector_store(monkeypatch):
    monkeypatch.setattr(vector_store, "get_cached_response", lambda *_, **__: None)
    monkeypatch.setattr(vector_store, "build_retrieval_context", lambda *_, **__: "")
    monkeypatch.setattr(vector_store, "cache_response", lambda *_, **__: None)


def test_extract_impact_candidates_prefers_llm(monkeypatch):
    stub_vector_store(monkeypatch)
    monkeypatch.setattr(
        scenario_mapping.llm_client,
        "score_impacts",
        lambda text, top_n=3, context=None: [("NVDA", 0.9), ("XLF", -0.7), ("AMD", 0.6)],
    )
    impacts = scenario_mapping.extract_impact_candidates("Fed cuts rates aggressively", top_n=3)
    assert impacts[0][0] == "NVDA"
    tickers = [symbol for symbol, _ in impacts]
    assert "XLF" in tickers
    assert impacts[tickers.index("XLF")][1] < 0


def test_extract_impact_candidates_fallback_to_keywords(monkeypatch):
    stub_vector_store(monkeypatch)
    monkeypatch.setattr(scenario_mapping.llm_client, "score_impacts", lambda text, top_n=3, context=None: [])
    impacts = scenario_mapping.extract_impact_candidates("What happens if we go to war with Mexico?", top_n=3)
    tickers = {ticker for ticker, _ in impacts}
    assert {"LMT", "RTX", "NOC"}.intersection(tickers)


def fake_provider_positive_negative():
    return (
        "stub",
        lambda headline, top_n, ctx: """```json
        {
            \"summary\": \"Stimulus drives risk assets higher, hurts duration\",
            \"positive_impacts\": [
                {\"symbol\": \"iwm\", \"weight\": 0.92},
                {\"symbol\": \"nvda\", \"weight\": 0.8}
            ],
            \"negative_impacts\": [
                {\"symbol\": \"tlt\", \"weight\": 0.7}
            ]
        }
        ```""",
    )


def test_score_impacts_normalizes_llm_payload(monkeypatch):
    stub_vector_store(monkeypatch)
    clear_llm_cache()
    monkeypatch.setattr(llm_client, "_choose_provider", fake_provider_positive_negative)

    impacts = llm_client.score_impacts("Stimulus for small caps", top_n=3)
    assert impacts == [("IWM", 0.92), ("NVDA", 0.8), ("TLT", -0.7)]


def test_score_impacts_handles_invalid_response(monkeypatch):
    stub_vector_store(monkeypatch)
    clear_llm_cache()
    monkeypatch.setattr(llm_client, "_choose_provider", lambda: ("stub", lambda headline, top_n, ctx: "not json"))
    impacts = llm_client.score_impacts("Headline", top_n=3)
    assert impacts == []


def test_context_sentiment():
    derived = context.derive_context("Stimulus boost for semiconductor manufacturing", top_n=5)
    assert derived["sentiment"] > 0
    assert derived["candidates"]

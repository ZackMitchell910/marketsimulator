from __future__ import annotations

import importlib

from src.data.events import vector_store as vector_store_module


def test_vector_store_roundtrip(tmp_path, monkeypatch):
    store_path = tmp_path / "history.jsonl"
    monkeypatch.setenv("MARKETTWIN_SCENARIO_STORE", str(store_path))
    importlib.reload(vector_store_module)

    assert vector_store_module.get_cached_response("Fed cuts rates") is None

    vector_store_module.cache_response(
        headline="Fed cuts rates",
        summary="Rates reduced, risk assets bid",
        positive=[{"symbol": "IWM", "weight": 0.8}],
        negative=[{"symbol": "TLT", "weight": -0.6}],
        combined=[("IWM", 0.8), ("TLT", -0.6)],
    )

    cached = vector_store_module.get_cached_response("Fed cuts rates")
    assert cached is not None
    assert cached["combined"][0]["symbol"] == "IWM"

    monkeypatch.delenv("MARKETTWIN_SCENARIO_STORE", raising=False)
    importlib.reload(vector_store_module)

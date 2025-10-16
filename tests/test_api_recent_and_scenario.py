import pytest
from fastapi.testclient import TestClient

from src.api import main


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(main, "_INGEST_API_KEY", None)
    main._RECENT.clear()
    client = TestClient(main.app)
    yield client
    main._RECENT.clear()


def test_recent_returns_204_when_empty(client):
    response = client.get("/recent")
    assert response.status_code == 204
    assert response.json() == []


def test_recent_returns_events_when_available(client):
    main._RECENT.append({"event": "tick", "ts": "2025-01-01T00:00:00Z"})
    response = client.get("/recent?n=1")
    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert body[0]["event"] == "tick"


def test_scenario_timestamps_are_utc_with_z(client):
    payload = {"text": "Unexpected rate hike by the Federal Reserve", "steps": 5}
    response = client.post("/scenario", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert body["generated_at"].endswith("Z")
    for impact in body["impacts"]:
        assert "baseline_price" in impact
        assert "projected_price" in impact
        assert "current_price" in impact
        for candle in impact["projection"]:
            assert candle["timestamp"].endswith("Z")

import pytest
from fastapi.testclient import TestClient

from src.api import main


@pytest.fixture()
def client():
    main._RECENT.clear()
    client = TestClient(main.app)
    yield client
    main._RECENT.clear()


def test_ingest_missing_api_key_returns_401(client, monkeypatch):
    monkeypatch.setattr(main, "_INGEST_API_KEY", "super-secret")
    response = client.post("/ingest", json={"event": "tick"})
    assert response.status_code == 401
    assert response.json()["detail"] == "Missing API key"


def test_ingest_with_valid_api_key_succeeds(client, monkeypatch):
    monkeypatch.setattr(main, "_INGEST_API_KEY", "super-secret")
    response = client.post("/ingest", json={"event": "tick"}, headers={"x-api-key": "super-secret"})
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "ok"
    assert body["buffer_size"] == 1

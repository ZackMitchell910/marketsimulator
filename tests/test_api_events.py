import asyncio
import json

from fastapi.testclient import TestClient

from src.api import main


def test_events_stream_returns_backlog(monkeypatch):
    with main._EVENT_STORES_LOCK:
        main._EVENT_STORES.clear()

    event = {
        "run_id": "test-run",
        "type": "tick",
        "symbol": "SPY",
        "price": 123.45,
        "timestamp": "2025-10-16T00:00:00Z",
    }
    asyncio.run(main.publish_event("test-run", event))

    with TestClient(main.app) as client:
        with client.stream("GET", "/events?run_id=test-run") as response:
            assert response.status_code == 200
            data_lines = []
            for line in response.iter_lines():
                if line:
                    text = line.decode() if isinstance(line, bytes) else line
                    data_lines.append(text)
                if len(data_lines) >= 1:
                    break
            assert data_lines
            assert data_lines[0].startswith("data: ")
            payload = json.loads(data_lines[0][6:])
            assert payload["run_id"] == "test-run"
            assert payload["type"] == "tick"

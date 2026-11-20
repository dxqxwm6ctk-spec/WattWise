"""The phone app finds the server by a UDP announcement or a QR code."""

import json

from fastapi.testclient import TestClient

from backend import discovery
from backend.main import app


def test_announcement_has_only_app_name_and_port(monkeypatch):
    monkeypatch.setenv("WATTWISE_PORT", "8123")
    msg = json.loads(discovery.announcement())
    assert msg == {"app": "wattwise", "port": 8123}


def test_connect_info_and_qr():
    with TestClient(app) as client:
        info = client.get("/api/connect").json()
        assert info["url"].startswith("http://") and info["url"].endswith(":8000")
        qr = client.get("/api/connect/qr.svg")
        assert qr.status_code == 200
        assert qr.headers["content-type"].startswith("image/svg+xml")
        assert "<svg" in qr.text
        assert client.get("/api/health").json() == {"ok": True, "app": "wattwise"}

"""Test config: force MOCK_MODE before any project import, patch latencies to ~0."""
import os
import sys

# Must be set before importing config/main/providers (they read env at import).
os.environ["MOCK_MODE"] = "1"
os.environ["DEMO_FALLBACK"] = "0"
os.environ["LANGFUSE_ENABLED"] = "0"
os.environ.setdefault("PUBLIC_BASE_URL", "http://localhost:8000")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient

import providers
import main

# Make the mock demo latencies instant for tests.
providers.LATENCY_LITE = 0.01
providers.LATENCY_NB2 = 0.01
providers.LATENCY_REEL = 0.01
providers.LATENCY_DIRECTOR = 0.01
providers.LATENCY_DRIVE = 0.01


@pytest.fixture()
def client():
    # Fresh in-memory store per test.
    main.sessions_db.clear()
    main.assets_db.clear()
    with TestClient(main.app) as c:
        yield c


@pytest.fixture()
def session_id(client):
    files = {"file": ("product.jpg", b"fake-image-bytes", "image/jpeg")}
    res = client.post("/api/session", files=files)
    assert res.status_code == 200
    return res.json()["session_id"]

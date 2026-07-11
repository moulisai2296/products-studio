"""End-to-end API tests in MOCK_MODE (no external deps)."""


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["mock_mode"] is True


def test_create_session_returns_product(client):
    files = {"file": ("saree.jpg", b"bytes", "image/jpeg")}
    r = client.post("/api/session", files=files)
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"]
    assert body["product_name"]  # mock returns "Saree"


def test_generate_angles_returns_four(client, session_id):
    r = client.post("/api/generate-angles", data={"session_id": session_id})
    assert r.status_code == 200
    assets = r.json()["assets"]
    assert len(assets) == 4
    for a in assets:
        assert a["kind"] == "angle"
        assert a["url"].startswith("http")
        assert a["cost_usd"] > 0
        assert a["model"]


def test_session_never_leaks_base64(client, session_id):
    client.post("/api/generate-angles", data={"session_id": session_id})
    r = client.get(f"/api/session/{session_id}")
    assert r.status_code == 200
    session = r.json()["session"]
    assert "product_b64" not in session
    assert "mime_type" not in session


def test_reel_ready_after_angles(client, session_id):
    # Background reel runs (TestClient executes background tasks); latency ~0.
    client.post("/api/generate-angles", data={"session_id": session_id})
    r = client.get(f"/api/session/{session_id}")
    assert r.json()["session"]["reel_status"] == "ready"


def test_edit_returns_asset(client, session_id):
    r = client.post("/api/edit", json={"session_id": session_id, "instruction": "on a model at a wedding"})
    assert r.status_code == 200
    body = r.json()
    assert body["asset"] is not None
    assert body["asset"]["kind"] == "edit"
    assert body["message"] is None


def test_approve_flows_to_store(client, session_id):
    ar = client.post("/api/generate-angles", data={"session_id": session_id})
    first = ar.json()["assets"][0]["id"]

    sr = client.post(f"/api/assets/{first}/status", json={"status": "approved"})
    assert sr.status_code == 200
    assert sr.json()["status"] == "approved"

    store = client.get(f"/api/store/{session_id}").json()
    approved_ids = [a["id"] for a in store["assets"]]
    assert first in approved_ids
    assert store["reel_url"] is not None  # reel ready in mock


def test_reanimate_hint_on_fresh_hero(client, session_id):
    ar = client.post("/api/generate-angles", data={"session_id": session_id})
    # angle[0] is the reel seed; approving angle[1] should offer re-animate.
    second = ar.json()["assets"][1]["id"]
    sr = client.post(f"/api/assets/{second}/status", json={"status": "approved"})
    assert sr.json()["reanimate_hint"] is True


def test_admin_sums_cost(client, session_id):
    client.post("/api/generate-angles", data={"session_id": session_id})
    r = client.get(f"/api/admin/{session_id}")
    body = r.json()
    assert body["total_cost"] > 0
    assert len(body["assets"]) == 4


def test_unknown_session_404(client):
    assert client.get("/api/session/nope").status_code == 404
    assert client.post("/api/edit", json={"session_id": "nope", "instruction": "x"}).status_code == 404

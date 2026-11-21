import pytest
from fastapi.testclient import TestClient
from stitchcraft_api.app import create_app


@pytest.fixture()
def client(tmp_path):
    return TestClient(create_app(cache_dir=tmp_path))


def test_health(client):
    assert client.get("/api/v1/health").json() == {"status": "ok"}


def test_dialects(client):
    ids = [d["id"] for d in client.get("/api/v1/dialects").json()]
    assert ids == ["de", "en-UK", "en-US"]


def test_stitches_vocabulary(client):
    data = client.get("/api/v1/stitches", params={"dialect": "en-UK"}).json()
    assert data["stitches"]["sc"][0] == "dc"


def test_validate_returns_codes_and_counts(client):
    r = client.post("/api/v1/validate", json={"text": "6 fM in MR\n6x zun (13)", "dialect": "de"})
    body = r.json()
    assert r.status_code == 200
    assert body["ok"] is False
    assert body["diagnostics"][0]["code"] == "E_COUNT_MISMATCH"
    assert body["diagnostics"][0]["params"] == {"row": 2, "expected": 13, "actual": 12}


def test_unknown_dialect_is_422(client):
    r = client.post("/api/v1/validate", json={"text": "x", "dialect": "fr"})
    assert r.status_code == 422


def test_parse_returns_ir(client):
    r = client.post("/api/v1/parse", json={"text": "Rd. 2: 6x zun (12)", "dialect": "de"})
    row = r.json()["pattern"]["parts"][0]["rows"][0]
    assert row["number"] == 2 and row["expected_count"] == 12


def test_preview_lifecycle_and_cache(client, tmp_path):
    body = {"text": "6 fM in MR (6)\n6x zun (12)", "dialect": "de", "params": {"fill": 0.5}}
    r = client.post("/api/v1/previews", json=body)
    assert r.status_code == 200
    first = r.json()
    assert first["status"] == "done" and first["stats"]["stitches"] == 18
    pid = first["id"]
    assert client.get(f"/api/v1/previews/{pid}/yarn.bin").content[:4] == b"SCYN"
    assert client.get(f"/api/v1/previews/{pid}/model.glb").content[:4] == b"glTF"
    assert client.get(f"/api/v1/previews/{pid}/shape.json").json()["key"] == pid
    events = client.get(f"/api/v1/previews/{pid}/events").text
    assert "event: done" in events
    again = client.post("/api/v1/previews", json=body).json()
    assert again["id"] == pid and again["cached"] is True


def test_preview_without_stitches_is_422(client):
    r = client.post("/api/v1/previews", json={"text": "nur Prosa hier", "dialect": "de"})
    assert r.status_code == 422
    assert r.json()["detail"]["diagnostics"][0]["code"] == "W_PROSE"


def test_unknown_preview_is_404(client):
    assert client.get("/api/v1/previews/deadbeef/yarn.bin").status_code == 404

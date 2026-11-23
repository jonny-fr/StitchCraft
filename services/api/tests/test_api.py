import json
import time

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


BODY = {"text": "6 fM in MR (6)\n6x zun (12)", "dialect": "de", "params": {"fill": 0.5}}


def sse(text):
    events = []
    for block in text.strip().split("\n\n"):
        name, data = block.split("\n")
        events.append((name.removeprefix("event: "), json.loads(data.removeprefix("data: "))))
    return events


def test_preview_runs_in_background_and_streams_progress(client):
    first = client.post("/api/v1/previews", json=BODY).json()
    assert first["status"] == "running" and first["cached"] is False
    pid = first["id"]
    events = sse(client.get(f"/api/v1/previews/{pid}/events").text)
    names = [n for n, _ in events]
    assert names[-1] == "done" and events[-1][1] == {"id": pid}
    stages = [d["stage"] for n, d in events if n == "progress"]
    assert stages[:3] == ["validate", "shape", "yarn"] and "export" in stages
    fractions = [d["fraction"] for n, d in events if n == "progress"]
    assert fractions == sorted(fractions) and fractions[-1] == 1.0
    assert client.get(f"/api/v1/previews/{pid}/yarn.bin").content[:4] == b"SCYN"
    assert client.get(f"/api/v1/previews/{pid}/model.glb").content[:4] == b"glTF"
    assert client.get(f"/api/v1/previews/{pid}/shape.json").json()["key"] == pid


def test_cached_preview_is_done_immediately(client):
    pid = client.post("/api/v1/previews", json=BODY).json()["id"]
    client.get(f"/api/v1/previews/{pid}/events")  # wait for the job
    again = client.post("/api/v1/previews", json=BODY).json()
    assert again["id"] == pid and again["cached"] is True and again["status"] == "done"
    assert again["stats"]["stitches"] == 18
    assert [n for n, _ in sse(client.get(f"/api/v1/previews/{pid}/events").text)] == [
        "progress",
        "done",
    ]


def test_files_are_404_until_the_preview_is_done(client, monkeypatch):
    import stitchcraft_api.app as app_module

    real = app_module.preview

    def slow(*args, **kwargs):
        time.sleep(0.3)
        return real(*args, **kwargs)

    monkeypatch.setattr(app_module, "preview", slow)
    pid = client.post("/api/v1/previews", json=BODY).json()["id"]
    assert client.get(f"/api/v1/previews/{pid}/yarn.bin").status_code == 404
    client.get(f"/api/v1/previews/{pid}/events")
    assert client.get(f"/api/v1/previews/{pid}/yarn.bin").status_code == 200


def test_duplicate_post_starts_no_second_job(client, monkeypatch):
    import stitchcraft_api.app as app_module

    real = app_module.preview
    calls = []

    def counting(*args, **kwargs):
        calls.append(1)
        time.sleep(0.3)
        return real(*args, **kwargs)

    monkeypatch.setattr(app_module, "preview", counting)
    a = client.post("/api/v1/previews", json=BODY).json()
    b = client.post("/api/v1/previews", json=BODY).json()
    assert a["id"] == b["id"] and b["status"] == "running"
    client.get(f"/api/v1/previews/{a['id']}/events")
    assert len(calls) == 1


def test_job_failure_is_an_error_event(client, monkeypatch):
    import stitchcraft_api.app as app_module

    def boom(*args, **kwargs):
        raise RuntimeError("solver exploded")

    monkeypatch.setattr(app_module, "preview", boom)
    pid = client.post("/api/v1/previews", json=BODY).json()["id"]
    events = sse(client.get(f"/api/v1/previews/{pid}/events").text)
    assert events[-1] == ("error", {"message": "solver exploded"})
    assert client.get(f"/api/v1/previews/{pid}/yarn.bin").status_code == 404


def test_unknown_preview_events_is_404(client):
    assert client.get("/api/v1/previews/deadbeef/events").status_code == 404


def test_preview_without_stitches_is_422(client):
    r = client.post("/api/v1/previews", json={"text": "nur Prosa hier", "dialect": "de"})
    assert r.status_code == 422
    assert r.json()["detail"]["diagnostics"][0]["code"] == "W_PROSE"


def test_unknown_preview_is_404(client):
    assert client.get("/api/v1/previews/deadbeef/yarn.bin").status_code == 404


def test_too_large_preview_is_422_with_diagnostic(client):
    r = client.post("/api/v1/previews", json={"text": "Rd. 1: (1000 fM) x 1000", "dialect": "de"})
    assert r.status_code == 422
    assert r.json()["detail"]["diagnostics"][0]["code"] == "E_TOO_LARGE"


def test_colour_change_reuses_cached_preview(client):
    body = {"text": "6 fM in MR (6)\n6x zun (12)", "dialect": "de"}
    first = client.post("/api/v1/previews", json={**body, "params": {"color": "#ff0000"}}).json()
    client.get(f"/api/v1/previews/{first['id']}/events")
    again = client.post("/api/v1/previews", json={**body, "params": {"color": "#00ff00"}}).json()
    assert again["id"] == first["id"] and again["cached"] is True


def test_validate_auto_detects_dialect(client):
    r = client.post("/api/v1/validate", json={"text": "Rnd 1: 6 sc in MR (6)"})
    assert r.status_code == 200
    assert r.json()["dialect"] == "en-US"


def test_validate_auto_reports_ambiguity(client):
    r = client.post("/api/v1/validate", json={"text": "Rnd 1: 12 dc in MR (12)", "dialect": "auto"})
    (d,) = r.json()["diagnostics"]
    assert d["code"] == "W_AMBIGUOUS_DIALECT"
    assert d["params"]["candidates"] == ["en-US", "en-UK"]


def test_vocabulary_lists_every_word_with_its_meaning(client):
    words = client.get("/api/v1/vocabulary", params={"dialect": "de"}).json()["words"]
    by_word = {w["word"]: w for w in words}
    assert by_word["fM"] == {"word": "fM", "category": "stitch", "canonical": "sc"}
    assert by_word["zun"]["category"] == "macro"
    assert by_word["nur hMg"] == {"word": "nur hMg", "category": "loop", "canonical": "blo"}
    assert by_word["Rd."]["category"] == "label"
    assert by_word["überspr."]["category"] == "skip"


def test_validate_rows_carry_their_source_line(client):
    r = client.post(
        "/api/v1/validate", json={"text": "\n6 fM in MR\nRd. 2-3: 6 fM", "dialect": "de"}
    )
    assert [row["line"] for row in r.json()["rows"]] == [2, 3, 3]

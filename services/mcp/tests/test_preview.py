import base64
import json

import pytest
from stitchcraft_mcp import server

from .samples import TINY

pytestmark = pytest.mark.anyio


async def test_render_preview_returns_glb_resource_stats_and_snapshot_note(client, cache):
    r = await client.call_tool("render_preview", {"text": TINY, "dialect": "de"})
    out = r.structured_content
    assert not r.is_error
    assert out["cached"] is False
    assert out["resources"]["model"] == f"stitchcraft://previews/{out['id']}/model.glb"
    assert out["stats"]["stitches"] == 18
    assert len(out["stats"]["size_cm"]) == 3
    assert out["notes"] == [
        "Snapshot-Dienst nicht verfügbar: Es gibt nur das GLB-Modell und die Statistik, kein PNG."
    ]
    assert all(f.exists() for f in (cache / out["id"]).iterdir())
    glb = (await client.read_resource(out["resources"]["model"])).contents[0]
    assert glb.mime_type == "model/gltf-binary"
    assert base64.b64decode(glb.blob)[:4] == b"glTF"
    shape = (await client.read_resource(out["resources"]["shape"])).contents[0]
    assert json.loads(base64.b64decode(shape.blob))["stitches"]


async def test_snapshot_note_is_localised(client):
    r = await client.call_tool("render_preview", {"text": TINY, "dialect": "de", "ui_locale": "en"})
    assert "Snapshot service unavailable" in r.structured_content["notes"][0]


async def test_second_call_is_a_cache_hit_without_simulation(client, monkeypatch):
    args = {"text": TINY, "dialect": "de"}
    first = (await client.call_tool("render_preview", args)).structured_content

    def boom(*a, **k):
        raise AssertionError("simulated again")

    monkeypatch.setattr(server, "preview", boom)
    second = (await client.call_tool("render_preview", args)).structured_content
    assert second["cached"] is True
    assert second["id"] == first["id"]
    assert second["stats"] == first["stats"]


async def test_color_does_not_change_the_key_but_yarn_does(client):
    a = (
        await client.call_tool("render_preview", {"text": TINY, "dialect": "de"})
    ).structured_content
    b = (
        await client.call_tool(
            "render_preview", {"text": TINY, "dialect": "de", "params": {"color": "#112233"}}
        )
    ).structured_content
    assert a["id"] == b["id"]
    c = (
        await client.call_tool(
            "render_preview", {"text": TINY, "dialect": "de", "params": {"yarn_mm": 3.0}}
        )
    ).structured_content
    assert c["id"] != a["id"]


async def test_progress_is_reported_when_the_client_asks(client):
    seen: list[tuple[float, str | None]] = []

    async def on_progress(progress, total, message):
        seen.append((progress, message))

    await client.call_tool(
        "render_preview", {"text": TINY, "dialect": "de"}, progress_callback=on_progress
    )
    assert seen
    assert seen[-1][0] == 1.0
    assert {m for _, m in seen} >= {"shape", "done"}


async def test_empty_pattern_is_tool_error_with_diagnostic(client):
    r = await client.call_tool("render_preview", {"text": "", "dialect": "de"})
    assert r.is_error
    assert "E_EMPTY_PATTERN" in r.content[0].text
    assert "keine Maschen" in r.content[0].text


@pytest.mark.parametrize(
    "arguments",
    [
        {"text": TINY, "dialect": "de", "view": "bottom"},
        {"text": TINY, "dialect": "de", "params": {"yarn_mm": 99}},
        {"text": TINY, "dialect": "de", "params": {"material": "silk"}},
        {"text": TINY, "dialect": "de", "params": {"bogus": 1}},
        {"text": TINY, "dialect": "de", "ui_locale": "fr"},
    ],
)
async def test_invalid_arguments_are_errors(client, arguments):
    r = await client.call_tool("render_preview", arguments)
    assert r.is_error


async def test_invalid_params_message_names_the_field(client):
    r = await client.call_tool("render_preview", {"text": TINY, "params": {"yarn_mm": 99}})
    assert "yarn_mm" in r.content[0].text


@pytest.mark.parametrize(
    "uri",
    [
        "stitchcraft://previews/unknown0123/model.glb",
        "stitchcraft://previews/..%2F..%2Fetc/model.glb",
        "stitchcraft://previews/../model.glb",
    ],
)
async def test_bad_resource_keys_are_errors(client, uri):
    with pytest.raises(Exception):  # noqa: B017 - SDK error type is transport specific
        await client.read_resource(uri)


async def test_incomplete_preview_is_not_served(client, cache):
    (cache / "abc123").mkdir()
    (cache / "abc123" / "model.glb").write_bytes(b"glTFpartial")
    with pytest.raises(Exception):  # noqa: B017
        await client.read_resource("stitchcraft://previews/abc123/model.glb")


@pytest.mark.slow
async def test_sphere_renders(client):
    from .samples import corpus

    r = await client.call_tool(
        "render_preview", {"text": corpus("en-US", "01-sphere.txt"), "dialect": "en-US"}
    )
    assert r.structured_content["stats"]["closed"] is True

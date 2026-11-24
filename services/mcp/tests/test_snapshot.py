import base64
import json
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from mcp.client import Client
from stitchcraft_mcp import snapshot
from stitchcraft_mcp.server import create_server

from .samples import TINY
from .test_transport import free_port

pytestmark = pytest.mark.anyio

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGP4z8DwHwAFAAH/q842iQAAAABJRU5ErkJggg=="
)


class Fake:
    """Snapshot service stand-in: counts and records /render calls."""

    def __init__(self, status=200, body=PNG):
        self.requests: list[dict] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers["content-length"])
                outer.requests.append(json.loads(self.rfile.read(length)))
                ctype = "image/png" if outer.status == 200 else "application/json"
                self.send_response(outer.status)
                self.send_header("content-type", ctype)
                self.send_header("content-length", str(len(outer.body)))
                self.end_headers()
                self.wfile.write(outer.body)

            def log_message(self, *args):
                pass

        self.status, self.body = status, body
        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture()
def fake(monkeypatch):
    f = Fake()
    monkeypatch.setenv("STITCHCRAFT_SNAPSHOT_URL", f.url)
    yield f
    f.close()


async def call(client, **extra):
    return await client.call_tool("render_preview", {"text": TINY, "dialect": "de", **extra})


async def test_png_is_returned_as_image_content_and_cached(client, cache, fake):
    r = await call(client)
    out = r.structured_content
    assert not r.is_error
    images = [c for c in r.content if c.type == "image"]
    assert len(images) == 1
    assert images[0].mime_type == "image/png"
    assert base64.b64decode(images[0].data) == PNG
    assert json.loads(r.content[0].text) == out
    uri = f"stitchcraft://previews/{out['id']}/efe6d2/front.png"
    assert out["resources"]["png"] == uri
    assert "notes" not in out
    assert fake.requests == [
        {"key": out["id"], "view": "front", "color": "efe6d2", "material": "cotton"}
    ]
    assert (cache / out["id"] / snapshot.png_name("efe6d2", "front")).read_bytes() == PNG

    again = await call(client)
    assert again.structured_content["cached"] is True
    assert len(fake.requests) == 1  # served from the cache
    assert any(c.type == "image" for c in again.content)

    res = (await client.read_resource(uri)).contents[0]
    assert res.mime_type == "image/png"
    assert base64.b64decode(res.blob) == PNG


async def test_other_colour_view_or_material_renders_again(client, fake):
    await call(client)
    await call(client, params={"color": "#C0392B"})
    await call(client, view="iso")
    await call(client, params={"material": "mohair"})  # new key: simulation and render
    assert [(q["color"], q["view"], q["material"]) for q in fake.requests] == [
        ("efe6d2", "front", "cotton"),
        ("c0392b", "front", "cotton"),
        ("efe6d2", "iso", "cotton"),
        ("efe6d2", "front", "mohair"),
    ]


async def test_unreachable_service_degrades_quickly_with_a_note(client, monkeypatch):
    monkeypatch.setenv("STITCHCRAFT_SNAPSHOT_URL", f"http://127.0.0.1:{free_port()}")
    await call(client)  # warm: the first call simulates
    start = time.monotonic()
    r = await call(client, ui_locale="en")
    assert time.monotonic() - start < 3
    out = r.structured_content
    assert not r.is_error
    assert out["stats"]["stitches"] == 18
    assert "png" not in out["resources"]
    assert all(c.type != "image" for c in r.content)
    assert out["notes"][0].startswith("Snapshot service failed (not reachable")


async def test_unresolvable_host_degrades_with_a_note(client, monkeypatch):
    monkeypatch.setenv("STITCHCRAFT_SNAPSHOT_URL", "http://snapshot.invalid:8770")
    r = await call(client)
    assert "Snapshot-Dienst nicht nutzbar" in r.structured_content["notes"][0]


@pytest.mark.parametrize(
    ("status", "body", "expect"),
    [
        (404, b'{"error": "unknown preview abc"}', "HTTP 404: unknown preview abc"),
        (502, b"<html>bad gateway</html>", "HTTP 502: <html>bad gateway</html>"),
        (200, b"not a png", "not a PNG"),
    ],
)
async def test_failing_service_gives_a_note_not_an_error(client, cache, fake, status, body, expect):
    fake.status, fake.body = status, body
    r = await call(client, ui_locale="en")
    assert not r.is_error
    assert expect in r.structured_content["notes"][0]
    assert not list(cache.glob("*/snapshots/*"))


async def test_timeout_gives_a_note(client, monkeypatch):
    class Silent(BaseHTTPRequestHandler):
        def do_POST(self):
            time.sleep(1.5)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Silent)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    monkeypatch.setenv("STITCHCRAFT_SNAPSHOT_URL", f"http://127.0.0.1:{server.server_port}")
    monkeypatch.setenv("STITCHCRAFT_SNAPSHOT_TIMEOUT", "0.3")
    try:
        r = await call(client, ui_locale="en")
    finally:
        server.shutdown()
        server.server_close()
    assert "timeout" in r.structured_content["notes"][0]


async def test_without_a_url_the_note_is_unavailable(client, monkeypatch):
    monkeypatch.delenv("STITCHCRAFT_SNAPSHOT_URL", raising=False)
    r = await call(client, ui_locale="en")
    assert r.structured_content["notes"] == [
        "Snapshot service unavailable: only the GLB model and statistics are returned, no PNG."
    ]
    assert all(c.type != "image" for c in r.content)


async def test_png_resource_rejects_bad_parameters(cache, fake):
    async with Client(create_server(cache)) as client:
        key = (await call(client)).structured_content["id"]
        good = f"stitchcraft://previews/{key}/efe6d2/front.png"
        assert (await client.read_resource(good)).contents
        bad = [
            f"stitchcraft://previews/{key}/EFE6D2/front.png",
            f"stitchcraft://previews/{key}/efe6d/front.png",
            f"stitchcraft://previews/{key}/efe6d2/bottom.png",
            f"stitchcraft://previews/{key}/c0392b/front.png",  # never rendered
            f"stitchcraft://previews/{key}/..%2F..%2Fx/front.png",
            "stitchcraft://previews/unknown0123/efe6d2/front.png",
            "stitchcraft://previews/..%2F..%2Fetc/efe6d2/front.png",
        ]
        for uri in bad:
            with pytest.raises(Exception):  # noqa: B017 - SDK error type is transport specific
                await client.read_resource(uri)


async def test_png_resource_does_not_serve_from_a_foreign_key(client, cache, fake):
    png = cache / "abc123" / snapshot.png_name("efe6d2", "front")
    png.parent.mkdir(parents=True)
    png.write_bytes(PNG)
    with pytest.raises(Exception):  # noqa: B017 - no meta.json: not a finished preview
        await client.read_resource("stitchcraft://previews/abc123/efe6d2/front.png")


async def test_png_is_rendered_again_after_the_look_changed(client, cache, fake, monkeypatch):
    await call(client)
    assert len(fake.requests) == 1
    await call(client)
    assert len(fake.requests) == 1  # cached
    # a new web build with a changed look bumps data/render.json
    version = snapshot.render_version()
    monkeypatch.setattr(snapshot, "render_version", lambda: version + 1)
    await call(client)
    assert len(fake.requests) == 2  # the PNG of the old look is not served


def test_render_version_is_part_of_the_png_path():
    assert snapshot.render_version() >= 2
    version = snapshot.render_version()
    assert snapshot.png_name("efe6d2", "front") == f"snapshots/r{version}/efe6d2-front.png"

"""Client for the PNG snapshot service (`services/snapshot`).

`STITCHCRAFT_SNAPSHOT_URL` unset means there is no service; `render_preview` then answers with the
GLB resource and statistics plus a note instead of failing. A configured but broken service raises
`SnapshotFailed`, which the tool turns into a note as well.
"""

from __future__ import annotations

import json
import os
from functools import cache as memo
from pathlib import Path

import httpx
from stitchcraft_core.data import data_dir

PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
CONNECT_TIMEOUT = 2.0  # compose sets the URL even when the profile is off: fail fast on DNS/refused


class SnapshotFailed(Exception):
    """The service is configured but did not deliver a PNG; `str(exc)` is the reason."""


def snapshot_url() -> str | None:
    return os.environ.get("STITCHCRAFT_SNAPSHOT_URL") or None


def render_timeout() -> float:
    return float(os.environ.get("STITCHCRAFT_SNAPSHOT_TIMEOUT", "90"))


@memo
def render_version() -> int:
    """Version of the viewer's look (`data/render.json`, shared with the web build).

    Part of the PNG path: after a change to the renderer, cached previews get a fresh snapshot.
    """
    return int(json.loads((data_dir() / "render.json").read_text(encoding="utf-8"))["version"])


def png_name(color: str, view: str) -> str:
    """PNG path inside a preview's cache directory."""
    return f"snapshots/r{render_version()}/{color}-{view}.png"


def png_path(cache: Path, key: str, color: str, view: str) -> Path:
    return cache / key / png_name(color, view)


async def render_png(cache: Path, key: str, view: str, color: str, material: str) -> bytes | None:
    """PNG of the cached preview `key`; None when no snapshot service is configured.

    `color` is 6 lower-case hex digits. A PNG already in the cache is returned without a render.
    """
    url = snapshot_url()
    if url is None:
        return None
    path = png_path(cache, key, color, view)
    if path.exists():
        return path.read_bytes()
    body = {"key": key, "view": view, "color": color, "material": material}
    timeout = httpx.Timeout(render_timeout(), connect=CONNECT_TIMEOUT)
    try:
        async with httpx.AsyncClient(timeout=timeout) as http:
            response = await http.post(f"{url.rstrip('/')}/render", json=body)
    except httpx.TimeoutException as exc:
        raise SnapshotFailed(f"timeout ({type(exc).__name__})") from exc
    except httpx.HTTPError as exc:
        raise SnapshotFailed(f"not reachable: {type(exc).__name__}") from exc
    if response.status_code != 200:
        raise SnapshotFailed(f"HTTP {response.status_code}: {_error_text(response)}")
    if not response.content.startswith(PNG_MAGIC):
        raise SnapshotFailed("response is not a PNG")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_bytes(response.content)
    tmp.replace(path)
    return response.content


def _error_text(response: httpx.Response) -> str:
    try:
        return str(response.json()["error"])[:200]
    except ValueError, KeyError, TypeError:
        return response.text[:200]

"""Hook for the PNG snapshot service (added in a later milestone).

`STITCHCRAFT_SNAPSHOT_URL` unset means there is no service; `render_preview` then answers with the
GLB resource and statistics plus a note instead of failing.
"""

from __future__ import annotations

import os


def snapshot_url() -> str | None:
    return os.environ.get("STITCHCRAFT_SNAPSHOT_URL") or None


async def render_png(key: str, view: str) -> bytes | None:
    """PNG of the cached preview `key` seen from `view`; None when no snapshot service is set."""
    if snapshot_url() is None:
        return None
    return None  # the snapshot client replaces this line

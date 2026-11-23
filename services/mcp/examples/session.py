"""Example MCP session against a running Streamable HTTP server (also the CI check).

uv run python services/mcp/examples/session.py [--url http://localhost:8765/mcp]
    [--png-out docs/mcp-preview.png] [--require-png]
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import sys
from pathlib import Path

from mcp.client import Client

AMBIGUOUS = "Rnd 1: 12 dc in MR (12)\nRnd 2: 12 dc (12)"  # US or UK terms?
CUP = "\n".join(
    [
        "Rnd 1: 6 sc in MR (6)",
        "Rnd 2: 6 inc (12)",
        "Rnd 3: (1 sc, inc) x6 (18)",
        "Rnd 4-6: 18 sc (18)",
    ]
)
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def show(title: str, data: object) -> None:
    print(f"\n== {title}")
    print(json.dumps(data, indent=2, ensure_ascii=False))


async def run(url: str, png_out: Path | None, require_png: bool) -> int:
    async with Client(url) as client:
        tools = [t.name for t in (await client.list_tools()).tools]
        show("tools", tools)

        r = await client.call_tool("validate_pattern", {"text": AMBIGUOUS, "ui_locale": "en"})
        out = r.structured_content
        show(
            "validate_pattern (dialect auto)", {k: out[k] for k in ("dialect", "ok", "diagnostics")}
        )

        r = await client.call_tool(
            "validate_pattern", {"text": AMBIGUOUS, "dialect": "en-US", "ui_locale": "en"}
        )
        out = r.structured_content
        show("validate_pattern (en-US)", {k: out[k] for k in ("dialect", "ok", "diagnostics")})

        r = await client.call_tool(
            "render_preview",
            {"text": CUP, "dialect": "en-US", "view": "iso", "ui_locale": "en"},
        )
        out = r.structured_content
        show("render_preview (iso)", out)
        images = [c for c in r.content if c.type == "image"]
        show(
            "content blocks",
            [c.type + (f" {c.mime_type}" if c.type == "image" else "") for c in r.content],
        )
        glb = (await client.read_resource(out["resources"]["model"])).contents[0]
        print(f"\nGLB resource: {glb.mime_type}, {len(base64.b64decode(glb.blob))} bytes")

        if images:
            png = base64.b64decode(images[0].data)
            if not png.startswith(PNG_MAGIC):
                print("image content is not a PNG", file=sys.stderr)
                return 1
            print(f"PNG image content: {len(png)} bytes")
            if png_out:
                png_out.write_bytes(png)
                print(f"saved to {png_out}")
        elif require_png:
            print("no PNG in the result: " + "; ".join(out.get("notes", [])), file=sys.stderr)
            return 1

        r = await client.call_tool("list_stitches", {"dialect": "en-US"})
        words = r.structured_content["vocabulary"]
        show(
            "list_stitches (en-US)",
            {"stitches": len(r.structured_content["stitches"]), "vocabulary": words[:3]},
        )
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://localhost:8765/mcp")
    parser.add_argument("--png-out", type=Path)
    parser.add_argument("--require-png", action="store_true", help="exit 1 without a PNG")
    args = parser.parse_args()
    sys.exit(asyncio.run(run(args.url, args.png_out, args.require_png)))


if __name__ == "__main__":
    main()

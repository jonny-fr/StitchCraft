"""MCP server: validate, parse, preview and list stitches over stdio or Streamable HTTP."""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
from pathlib import Path
from typing import Annotated, Any, Literal

import anyio
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp_types import CallToolResult, ImageContent, TextContent
from pydantic import Field, ValidationError
from stitchcraft_api.schemas import ParamsIn, PatternIn
from stitchcraft_core.data import load_toml
from stitchcraft_core.export import write_preview
from stitchcraft_core.messages import LOCALES, diagnostic_message, message
from stitchcraft_core.notation.dialect import available_dialects, vocabulary
from stitchcraft_core.params import Params
from stitchcraft_core.pipeline import PreviewError, cache_key, preview
from stitchcraft_core.serialize import parse_dict, validation_dict
from stitchcraft_core.validate import validate

from stitchcraft_mcp import snapshot
from stitchcraft_mcp.snapshot import SnapshotFailed

VIEWS = ("front", "side", "top", "iso")
DEFAULT_PORT = 8765
KEY = re.compile(r"[0-9a-zA-Z]+")
COLOR = re.compile(r"[0-9a-f]{6}")
FILES = {"model.glb": "model/gltf-binary", "shape.json": "application/json"}

Text = Annotated[str, Field(description="Crochet pattern, one round/row per line")]
Dialect = Annotated[str, Field(description="de, en-US, en-UK or auto (detect)")]
UiLocale = Annotated[str, Field(description="Language of messages: de or en")]


def _locale(ui_locale: str) -> str:
    if ui_locale not in LOCALES:
        raise ToolError(f"unknown ui_locale {ui_locale!r}; use one of {', '.join(LOCALES)}")
    return ui_locale


def _pattern(text: str, dialect: str) -> PatternIn:
    try:
        return PatternIn(text=text, dialect=dialect)
    except ValidationError as exc:
        raise ToolError(_invalid(exc)) from exc


def _params(raw: dict[str, Any] | None) -> ParamsIn:
    unknown = sorted(set(raw or {}) - set(ParamsIn.model_fields))
    if unknown:
        raise ToolError(f"unknown params: {', '.join(unknown)}")
    try:
        return ParamsIn(**(raw or {}))
    except ValidationError as exc:
        raise ToolError(f"invalid params: {_invalid(exc)}") from exc


def _invalid(exc: ValidationError) -> str:
    return "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in exc.errors())


def _localised(diagnostics: list[dict], locale: str) -> list[dict]:
    """Add line, col and the message in `locale` to `diagnostic_dict` entries."""
    out = []
    for d in diagnostics:
        span = d["span"] or {}
        line, col = span.get("line"), span.get("col")
        text = diagnostic_message(d["code"], d["params"], line, locale)
        out.append({**d, "line": line, "col": col, "message": text})
    return out


def create_server(cache_dir: Path | None = None) -> MCPServer:
    cache = Path(cache_dir or os.environ.get("STITCHCRAFT_CACHE", ".cache/previews"))
    cache.mkdir(parents=True, exist_ok=True)
    mcp = MCPServer(
        "stitchcraft",
        instructions=(
            "Validate and preview crochet patterns (dialects de, en-US, en-UK). "
            "Start with validate_pattern; render_preview returns a 3D model resource."
        ),
    )

    @mcp.tool()
    def validate_pattern(
        text: Text, dialect: Dialect = "auto", ui_locale: UiLocale = "de"
    ) -> dict[str, Any]:
        """Check a pattern: detected dialect, diagnostics with line/column and message, and
        expected vs. counted stitches per round/row."""
        locale = _locale(ui_locale)
        body = _pattern(text, dialect)
        result = validate(body.text, dialect=body.dialect)
        out = validation_dict(result)
        out["diagnostics"] = _localised(out["diagnostics"], locale)
        out["rows"] = [
            {**r, "matches": r["expected"] is None or r["expected"] == r["actual"]}
            for r in result.rows
        ]
        return out

    @mcp.tool()
    def parse_pattern(text: Text, dialect: Dialect = "auto") -> dict[str, Any]:
        """Parse a pattern into its canonical intermediate representation (JSON)."""
        body = _pattern(text, dialect)
        return parse_dict(body.text, body.dialect)

    @mcp.tool()
    def list_stitches(
        dialect: Annotated[str, Field(description="de, en-US or en-UK")],
    ) -> dict[str, Any]:
        """Stitch library and vocabulary of a dialect with canonical stitch types."""
        if dialect not in available_dialects():
            raise ToolError(
                f"unknown dialect {dialect!r}; use one of {', '.join(available_dialects())}"
            )
        raw = load_toml("dialects", f"{dialect}.toml")
        return {
            "dialect": dialect,
            "stitches": raw["stitches"],
            "macros": raw["macros"],
            "vocabulary": vocabulary(dialect),
        }

    @mcp.tool()
    async def render_preview(
        text: Text,
        ctx: Context,
        dialect: Dialect = "auto",
        params: Annotated[
            dict[str, Any] | None,
            Field(
                description=(
                    "Optional: yarn_mm, hook_mm, gauge_stitches, gauge_rows, fill (0-1), "
                    "handedness, right_side_out, material (cotton/acrylic/mohair), color, seed"
                )
            ),
        ] = None,
        view: Annotated[
            Literal["front", "side", "top", "iso"], Field(description="Camera for the PNG")
        ] = "front",
        ui_locale: UiLocale = "de",
    ) -> Annotated[CallToolResult, dict[str, Any]]:
        """Simulate the yarn and return the 3D model (GLB resource) with statistics and, when the
        snapshot service runs, a PNG of the piece from `view`. Results are cached by content, so
        repeating a call is instant."""
        locale = _locale(ui_locale)
        body = _pattern(text, dialect)
        params_in = _params(params)
        core_params = Params(**params_in.model_dump())
        key = cache_key(body.text, body.dialect, core_params)
        meta_path = cache / key / "meta.json"
        cached = meta_path.exists()
        if cached:
            meta = json.loads(meta_path.read_text())
            await ctx.report_progress(1.0, 1.0, "cached")
        else:
            meta = await _simulate(ctx, body, core_params, key, locale)
        color = core_params.color.lstrip("#").lower()
        uris = {
            "model": f"stitchcraft://previews/{key}/model.glb",
            "shape": f"stitchcraft://previews/{key}/shape.json",
        }
        notes: list[str] = []
        png: bytes | None = None
        try:
            png = await snapshot.render_png(cache, key, view, color, core_params.material)
        except SnapshotFailed as exc:
            notes.append(message("snapshot.failed", locale, reason=str(exc)))
        else:
            if png is None:
                notes.append(message("snapshot.unavailable", locale))
        if png is not None:
            uris["png"] = f"stitchcraft://previews/{key}/{color}/{view}.png"
        out: dict[str, Any] = {
            "id": key,
            "cached": cached,
            "view": view,
            "resources": uris,
            "stats": meta["stats"],
            "diagnostics": _localised(meta["diagnostics"], locale),
        }
        if notes:
            out["notes"] = notes
        content: list[TextContent | ImageContent] = [TextContent(type="text", text=json.dumps(out))]
        if png is not None:
            data = base64.b64encode(png).decode()
            content.append(ImageContent(type="image", data=data, mime_type="image/png"))
        return CallToolResult(content=content, structured_content=out)

    async def _simulate(ctx: Context, body: PatternIn, params: Params, key: str, locale: str):
        def run() -> dict:
            def progress(stage: str, fraction: float) -> None:
                anyio.from_thread.run(ctx.report_progress, fraction, 1.0, stage)

            result = preview(body.text, body.dialect, params, key, progress=progress)
            progress("export", 0.9)
            return write_preview(result, cache)

        try:
            # relaxation is CPU-bound: keep the event loop (and other sessions) responsive
            meta = await anyio.to_thread.run_sync(run)
        except PreviewError as exc:
            diags = _localised(validation_dict(exc.validation)["diagnostics"], locale)
            lines = "\n".join(f"- {d['code']}: {d['message']}" for d in diags)
            raise ToolError(f"{message('preview.nothing', locale)}\n{lines}") from exc
        await ctx.report_progress(1.0, 1.0, "done")
        return meta

    @mcp.resource("stitchcraft://previews/{key}/model.glb", mime_type=FILES["model.glb"])
    def preview_model(key: str) -> bytes:
        """Binary glTF of a preview created by render_preview."""
        return _read(key, "model.glb")

    @mcp.resource("stitchcraft://previews/{key}/shape.json", mime_type=FILES["shape.json"])
    def preview_shape(key: str) -> bytes:
        """Stitch positions and metadata of a preview created by render_preview."""
        return _read(key, "shape.json")

    @mcp.resource("stitchcraft://previews/{key}/{color}/{view}.png", mime_type="image/png")
    def preview_png(key: str, color: str, view: str) -> bytes:
        """PNG snapshot of a preview in yarn colour `color` (6 hex digits) from `view`."""
        if not COLOR.fullmatch(color) or view not in VIEWS:
            raise ValueError(f"unknown snapshot {color}/{view}")
        return _read(key, f"snapshots/{color}-{view}.png")

    def _read(key: str, name: str) -> bytes:
        path = cache / key / name
        if not KEY.fullmatch(key) or not (cache / key / "meta.json").exists() or not path.exists():
            raise ValueError(f"unknown preview {key!r}")
        return path.read_bytes()

    return mcp


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="stitchcraft-mcp", description=__doc__)
    parser.add_argument("transport", choices=["stdio", "http"], nargs="?", default="stdio")
    parser.add_argument("--host", default=os.environ.get("STITCHCRAFT_MCP_HOST", "127.0.0.1"))
    parser.add_argument(
        "--port", type=int, default=int(os.environ.get("STITCHCRAFT_MCP_PORT", DEFAULT_PORT))
    )
    args = parser.parse_args(argv)
    server = create_server()
    if args.transport == "stdio":
        server.run("stdio")
    else:
        server.run("streamable-http", host=args.host, port=args.port)


if __name__ == "__main__":
    main()

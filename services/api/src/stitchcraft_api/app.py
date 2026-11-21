"""FastAPI app: validation, parsing, previews (content-addressed disk cache)."""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response, StreamingResponse
from stitchcraft_core.data import load_toml
from stitchcraft_core.export import encode_yarn_bin, glb_bytes, shape_json
from stitchcraft_core.notation import parse
from stitchcraft_core.notation.dialect import available_dialects, load_dialect
from stitchcraft_core.params import Params
from stitchcraft_core.pipeline import PreviewError, cache_key, preview
from stitchcraft_core.serialize import diagnostic_dict, validation_dict
from stitchcraft_core.validate import validate

from stitchcraft_api.schemas import PatternIn, PreviewIn

FILES = {"yarn.bin": "application/octet-stream", "model.glb": "model/gltf-binary"}


def create_app(cache_dir: Path | None = None) -> FastAPI:
    cache = Path(cache_dir or os.environ.get("STITCHCRAFT_CACHE", ".cache/previews"))
    cache.mkdir(parents=True, exist_ok=True)
    app = FastAPI(title="Stitchcraft API", version="0.1.0")

    @app.get("/api/v1/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/v1/dialects")
    def dialects() -> list[dict]:
        return [{"id": d, "name": load_dialect(d).name} for d in available_dialects()]

    @app.get("/api/v1/stitches")
    def stitches(dialect: str = "de") -> dict:
        if dialect not in available_dialects():
            raise HTTPException(422, f"unknown dialect {dialect!r}")
        raw = load_toml("dialects", f"{dialect}.toml")
        return {"dialect": dialect, "stitches": raw["stitches"], "macros": raw["macros"]}

    @app.post("/api/v1/validate")
    def validate_pattern(body: PatternIn) -> dict:
        return validation_dict(validate(body.text, dialect=body.dialect))

    @app.post("/api/v1/parse")
    def parse_pattern(body: PatternIn) -> dict:
        result = parse(body.text, dialect=body.dialect)
        return {
            "pattern": json.loads(json.dumps(asdict(result.pattern), default=str)),
            "diagnostics": [diagnostic_dict(d) for d in result.diagnostics],
        }

    @app.post("/api/v1/previews")
    async def create_preview(body: PreviewIn) -> dict:
        params = Params(**body.params.model_dump())
        key = cache_key(body.text, body.dialect, params)
        target = cache / key
        meta = target / "meta.json"
        if meta.exists():
            return {**json.loads(meta.read_text()), "cached": True}
        try:
            result = await run_in_threadpool(preview, body.text, body.dialect, params)
        except PreviewError as exc:
            detail = {"diagnostics": validation_dict(exc.validation)["diagnostics"]}
            raise HTTPException(422, detail) from exc
        target.mkdir(parents=True, exist_ok=True)
        (target / "yarn.bin").write_bytes(encode_yarn_bin(result.yarn))
        (target / "model.glb").write_bytes(await run_in_threadpool(glb_bytes, result.yarn))
        (target / "shape.json").write_text(json.dumps(shape_json(result)))
        out = {
            "id": key,
            "status": "done",
            "stats": result.stats,
            "diagnostics": [diagnostic_dict(d) for d in result.validation.diagnostics],
        }
        meta.write_text(json.dumps(out))
        return {**out, "cached": False}

    def _file(pid: str, name: str) -> Path:
        path = cache / pid / name
        if not pid.isalnum() or not path.exists():
            raise HTTPException(404, "unknown preview")
        return path

    @app.get("/api/v1/previews/{pid}/events")
    def preview_events(pid: str) -> StreamingResponse:
        _file(pid, "meta.json")

        def stream():
            yield 'event: progress\ndata: {"stage": "done", "fraction": 1.0}\n\n'
            yield f'event: done\ndata: {{"id": "{pid}"}}\n\n'

        return StreamingResponse(stream(), media_type="text/event-stream")

    @app.get("/api/v1/previews/{pid}/shape.json")
    def preview_shape(pid: str) -> Response:
        return Response(_file(pid, "shape.json").read_bytes(), media_type="application/json")

    @app.get("/api/v1/previews/{pid}/{name}")
    def preview_file(pid: str, name: str) -> Response:
        if name not in FILES:
            raise HTTPException(404, "unknown file")
        return Response(_file(pid, name).read_bytes(), media_type=FILES[name])

    return app


app = create_app()

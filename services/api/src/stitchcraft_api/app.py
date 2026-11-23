"""FastAPI app: validation, parsing, previews (content-addressed disk cache)."""

from __future__ import annotations

import asyncio
import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import Response, StreamingResponse
from stitchcraft_core.data import load_toml
from stitchcraft_core.export import encode_yarn_bin, glb_bytes, point_colors, shape_json
from stitchcraft_core.notation import parse
from stitchcraft_core.notation.dialect import available_dialects, load_dialect, vocabulary
from stitchcraft_core.params import Params
from stitchcraft_core.pipeline import cache_key, preview
from stitchcraft_core.serialize import diagnostic_dict, validation_dict
from stitchcraft_core.validate import validate

from stitchcraft_api.schemas import PatternIn, PreviewIn

FILES = {"yarn.bin": "application/octet-stream", "model.glb": "model/gltf-binary"}


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


class _Job:
    """Progress log of one background preview; the SSE endpoint replays it."""

    def __init__(self, key: str) -> None:
        self.key = key
        self._lock = threading.Lock()
        self._events: list[tuple[str, dict]] = []
        self._finished = False
        self.error: str | None = None

    def report(self, stage: str, fraction: float) -> None:
        with self._lock:
            self._events.append(("progress", {"stage": stage, "fraction": fraction}))

    def finish(self) -> None:
        with self._lock:
            self._events.append(("progress", {"stage": "done", "fraction": 1.0}))
            self._events.append(("done", {"id": self.key}))
            self._finished = True

    def fail(self, message: str) -> None:
        with self._lock:
            self._events.append(("error", {"message": message}))
            self.error = message
            self._finished = True

    def snapshot(self, seen: int) -> tuple[list[tuple[str, dict]], bool]:
        with self._lock:
            return self._events[seen:], self._finished


def create_app(cache_dir: Path | None = None, max_jobs: int | None = None) -> FastAPI:
    cache = Path(cache_dir or os.environ.get("STITCHCRAFT_CACHE", ".cache/previews"))
    cache.mkdir(parents=True, exist_ok=True)
    # relaxations are CPU-bound: run a few at a time, the rest wait as "queued"
    workers = max_jobs or int(os.environ.get("STITCHCRAFT_JOBS", "2"))
    executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="preview")

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        executor.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(title="Stitchcraft API", version="0.1.0", lifespan=lifespan)

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

    @app.get("/api/v1/vocabulary")
    def vocabulary_words(dialect: str = "de") -> dict:
        if dialect not in available_dialects():
            raise HTTPException(422, f"unknown dialect {dialect!r}")
        return {"dialect": dialect, "words": vocabulary(dialect)}

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

    jobs: dict[str, _Job] = {}
    jobs_lock = threading.Lock()

    def _run(job: _Job, body: PreviewIn, params: Params, key: str) -> None:
        target = cache / key
        try:
            result = preview(body.text, body.dialect, params, key, progress=job.report)
            job.report("export", 0.9)
            target.mkdir(parents=True, exist_ok=True)
            (target / "yarn.bin").write_bytes(encode_yarn_bin(result.yarn))
            (target / "model.glb").write_bytes(glb_bytes(result.yarn, 8, point_colors(result)))
            (target / "shape.json").write_text(json.dumps(shape_json(result)))
            out = {
                "id": key,
                "status": "done",
                "stats": result.stats,
                "diagnostics": [diagnostic_dict(d) for d in result.validation.diagnostics],
            }
            (target / "meta.json").write_text(json.dumps(out))  # last: marks the preview complete
            job.finish()
        except Exception as exc:  # reported to the client as event: error
            job.fail(str(exc) or type(exc).__name__)

    @app.post("/api/v1/previews")
    def create_preview(body: PreviewIn) -> dict:
        params = Params(**body.params.model_dump())
        key = cache_key(body.text, body.dialect, params)
        meta = cache / key / "meta.json"
        if meta.exists():
            return {**json.loads(meta.read_text()), "cached": True}
        # synchronous validation: errors stay a 422 with diagnostics
        validation = validate(body.text, dialect=body.dialect)
        if not any(n.counting for n in validation.graph.nodes):
            detail = {"diagnostics": validation_dict(validation)["diagnostics"]}
            raise HTTPException(422, detail)
        with jobs_lock:
            job = jobs.get(key)
            if job is None or job.error is not None:
                job = jobs[key] = _Job(key)
                job.report("queued", 0.0)
                executor.submit(_run, job, body, params, key)
        return {"id": key, "status": "running", "cached": False}

    def _file(pid: str, name: str) -> Path:
        path = cache / pid / name
        if not pid.isalnum() or not (cache / pid / "meta.json").exists() or not path.exists():
            raise HTTPException(404, "unknown preview")
        return path

    @app.get("/api/v1/previews/{pid}/events")
    async def preview_events(pid: str) -> StreamingResponse:
        job = jobs.get(pid) if pid.isalnum() else None
        done = pid.isalnum() and (cache / pid / "meta.json").exists()
        if job is None and not done:
            raise HTTPException(404, "unknown preview")

        async def stream():
            if done or job is None:
                yield _sse("progress", {"stage": "done", "fraction": 1.0})
                yield _sse("done", {"id": pid})
                return
            seen = 0
            while True:
                events, finished = job.snapshot(seen)
                for name, data in events:
                    yield _sse(name, data)
                seen += len(events)
                if finished:
                    return
                await asyncio.sleep(0.05)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"cache-control": "no-cache", "x-accel-buffering": "no"},
        )

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

"""Text -> validated graph -> relaxed shape -> yarn path, with a content-addressed key."""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field

import numpy as np

from stitchcraft_core import __version__
from stitchcraft_core.ir import Pattern
from stitchcraft_core.notation import parse
from stitchcraft_core.params import Params
from stitchcraft_core.sim import Shape, relax
from stitchcraft_core.validate import ValidationResult, validate
from stitchcraft_core.yarn import YarnPath, build_yarn
from stitchcraft_core.yarn.templates import templates_version


class PreviewError(ValueError):
    def __init__(self, validation: ValidationResult):
        super().__init__("pattern has no stitches to simulate")
        self.validation = validation


@dataclass
class Preview:
    key: str
    validation: ValidationResult
    shape: Shape
    yarn: YarnPath
    stats: dict[str, object] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.validation.ok

    @property
    def yarn_hash(self) -> str:
        return hashlib.sha256(self.yarn.points.tobytes()).hexdigest()


def _strip_spans(obj):
    if isinstance(obj, dict):
        return {k: _strip_spans(v) for k, v in obj.items() if k != "span"}
    if isinstance(obj, list):
        return [_strip_spans(v) for v in obj]
    return obj


def normalised_ir(pattern: Pattern) -> str:
    return json.dumps(_strip_spans(asdict(pattern)), sort_keys=True, default=str)


def cache_key(text: str, dialect: str, params: Params) -> str:
    ir = normalised_ir(parse(text, dialect=dialect).pattern)
    blob = json.dumps(
        {
            "ir": ir,
            "params": params.cache_key(),
            "templates": templates_version(),
            "core": __version__,
        },
        sort_keys=True,
    )
    return hashlib.sha256(blob.encode()).hexdigest()[:32]


def preview(text: str, dialect: str, params: Params, key: str | None = None) -> Preview:
    timings = {}
    t0 = time.perf_counter()
    validation = validate(text, dialect=dialect)
    graph = validation.graph
    if not any(n.counting for n in graph.nodes):
        raise PreviewError(validation)
    timings["validate_ms"] = (time.perf_counter() - t0) * 1000
    t1 = time.perf_counter()
    shape = relax(graph, params)
    timings["shape_ms"] = (time.perf_counter() - t1) * 1000
    t2 = time.perf_counter()
    yarn = build_yarn(graph, shape, params)
    timings["yarn_ms"] = (time.perf_counter() - t2) * 1000

    centred = yarn.points - yarn.points.mean(axis=0)
    _, _, axes = np.linalg.svd(centred[:: max(1, len(centred) // 4000)], full_matrices=False)
    extents = np.ptp(centred @ axes.T, axis=0) + 2 * params.yarn_radius_mm
    stats = {
        "stitches": validation.total_stitches,
        "rows": len(graph.rows),
        "size_cm": [round(float(e) / 10, 1) for e in extents],
        "yarn_length_m": round(
            float(np.linalg.norm(np.diff(yarn.points, axis=0), axis=1).sum()) / 1000, 2
        ),
        "closed": shape.closed,
        "timings": {k: round(v, 1) for k, v in timings.items()},
    }
    return Preview(key or cache_key(text, dialect, params), validation, shape, yarn, stats)

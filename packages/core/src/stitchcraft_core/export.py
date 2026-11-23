"""Exports: compact binary yarn path for the viewer, GLB tube mesh, shape JSON."""

from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from stitchcraft_core import colors
from stitchcraft_core.serialize import diagnostic_dict
from stitchcraft_core.yarn import YarnPath

if TYPE_CHECKING:
    from stitchcraft_core.pipeline import Preview

MAGIC = b"SCYN"
VERSION = 1
HEADER = struct.Struct("<4sIIII")  # magic, version, points, segments, reserved


def encode_yarn_bin(yarn: YarnPath) -> bytes:
    """Layout (little endian): header | float32 xyz * n | float32 radius * n |
    uint32 stitch id * n | uint32 segment offset * s."""
    n = len(yarn.points)
    s = len(yarn.segment_offsets)
    return b"".join(
        [
            HEADER.pack(MAGIC, VERSION, n, s, 0),
            yarn.points.astype("<f4").tobytes(),
            yarn.radius.astype("<f4").tobytes(),
            yarn.stitch_ids.astype("<u4").tobytes(),
            yarn.segment_offsets.astype("<u4").tobytes(),
        ]
    )


def decode_yarn_bin(blob: bytes) -> dict[str, np.ndarray]:
    magic, version, n, s, _ = HEADER.unpack_from(blob)
    if magic != MAGIC or version != VERSION:
        raise ValueError("not a Stitchcraft yarn path")
    off = HEADER.size
    points = np.frombuffer(blob, "<f4", n * 3, off).reshape(n, 3)
    off += n * 12
    radius = np.frombuffer(blob, "<f4", n, off)
    off += n * 4
    ids = np.frombuffer(blob, "<u4", n, off)
    off += n * 4
    segments = np.frombuffer(blob, "<u4", s, off)
    return {"points": points, "radius": radius, "stitch_ids": ids, "segment_offsets": segments}


def tube_mesh(yarn: YarnPath, sides: int = 8, rgba: np.ndarray | None = None):
    """Tube around the yarn centre line with parallel-transport frames.

    ``rgba``: optional (n, 4) uint8 per yarn point, exported as vertex colours."""
    import trimesh

    p = yarn.points
    tangent = np.gradient(p, axis=0)
    tangent /= np.maximum(np.linalg.norm(tangent, axis=1, keepdims=True), 1e-12)
    normal = np.zeros_like(p)
    ref = np.array([0.0, 0.0, 1.0]) if abs(tangent[0, 2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    normal[0] = np.cross(tangent[0], ref)
    normal[0] /= np.linalg.norm(normal[0])
    for i in range(1, len(p)):
        n = normal[i - 1] - (normal[i - 1] @ tangent[i]) * tangent[i]
        length = np.linalg.norm(n)
        normal[i] = n / length if length > 1e-12 else normal[i - 1]
    binormal = np.cross(tangent, normal)
    angles = 2 * np.pi * np.arange(sides) / sides
    ring = (
        np.cos(angles)[None, :, None] * normal[:, None]
        + np.sin(angles)[None, :, None] * binormal[:, None]
    )
    vertices = (p[:, None] + yarn.radius[:, None, None] * ring).reshape(-1, 3)
    ring_start = np.arange(len(p) - 1)[:, None] * sides
    j = np.arange(sides)[None, :]
    a = ring_start + j
    b = ring_start + (j + 1) % sides
    c = a + sides
    d = b + sides
    faces = np.concatenate([np.stack([a, b, c], -1), np.stack([b, d, c], -1)], axis=1).reshape(
        -1, 3
    )
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    if rgba is not None:
        mesh.visual = trimesh.visual.ColorVisuals(mesh, vertex_colors=np.repeat(rgba, sides, 0))
    mesh.vertex_attributes["_STITCH_ID"] = np.repeat(yarn.stitch_ids, sides).astype(np.float32)
    return mesh


def glb_bytes(yarn: YarnPath, sides: int = 8, rgba: np.ndarray | None = None) -> bytes:
    import trimesh

    return trimesh.exchange.gltf.export_glb(trimesh.Scene(tube_mesh(yarn, sides, rgba)))


def palette(p: Preview) -> list[dict[str, object]]:
    """The colours the piece uses, in order of first use, each with its hex."""
    used = list(dict.fromkeys(n.color for n in p.validation.graph.nodes))
    return colors.resolve(used, p.validation.pattern.palette)


def point_colors(p: Preview) -> np.ndarray:
    """(n, 4) uint8 RGBA per yarn point, from the colour of the stitch it belongs to."""
    by_ref = {
        c["ref"]: [int(str(c["hex"])[i : i + 2], 16) for i in (1, 3, 5)] + [255] for c in palette(p)
    }
    nodes = p.validation.graph.nodes
    return np.array([by_ref[nodes[i].color] for i in p.yarn.stitch_ids], dtype=np.uint8)


def shape_json(p: Preview) -> dict:
    g = p.validation.graph
    stitches = []
    for node in g.nodes:
        span = node.span
        stitches.append(
            {
                "id": node.id,
                "row": g.rows[node.row].number if node.row >= 0 else 0,
                "type": node.type,
                "op": node.op,
                "loop": node.loop,
                "counting": node.counting,
                "turning": node.turning,
                "color": node.color,
                "parents": node.parents,
                "position": [round(float(v), 3) for v in p.shape.positions[node.id]],
                "span": None
                if span is None
                else {"start": span.start, "end": span.end, "line": span.line, "col": span.col},
            }
        )
    rows = [
        {
            "number": r.number,
            "kind": r.kind,
            "stitches": len(g.counting_ids(r)),
            "expected": r.expected,
            "first": r.node_ids[0] if r.node_ids else None,
            "last": r.node_ids[-1] if r.node_ids else None,
        }
        for r in g.rows
    ]
    return {
        "key": p.key,
        "stats": p.stats,
        "palette": palette(p),
        "stitches": stitches,
        "rows": rows,
    }


def write_preview(p: Preview, cache_dir: Path) -> dict:
    """Write yarn.bin, model.glb, shape.json and, last, meta.json (marks it complete) to
    `<cache_dir>/<key>/`; returns the meta."""
    target = cache_dir / p.key
    target.mkdir(parents=True, exist_ok=True)
    (target / "yarn.bin").write_bytes(encode_yarn_bin(p.yarn))
    (target / "model.glb").write_bytes(glb_bytes(p.yarn, 8, point_colors(p)))
    (target / "shape.json").write_text(json.dumps(shape_json(p)))
    meta = {
        "id": p.key,
        "status": "done",
        "stats": p.stats,
        "diagnostics": [diagnostic_dict(d) for d in p.validation.diagnostics],
    }
    (target / "meta.json").write_text(json.dumps(meta))
    return meta

"""Exports: compact binary yarn path for the viewer, GLB tube mesh, shape JSON."""

from __future__ import annotations

import struct
from typing import TYPE_CHECKING

import numpy as np

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


def tube_mesh(yarn: YarnPath, sides: int = 8):
    """Tube around the yarn centre line with parallel-transport frames."""
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
    ring = np.cos(angles)[None, :, None] * normal[:, None] + np.sin(angles)[None, :, None] * binormal[:, None]
    vertices = (p[:, None] + yarn.radius[:, None, None] * ring).reshape(-1, 3)
    i = np.arange(len(p) - 1)[:, None] * sides
    j = np.arange(sides)[None, :]
    a = i + j
    b = i + (j + 1) % sides
    c = a + sides
    d = b + sides
    faces = np.concatenate([np.stack([a, b, c], -1), np.stack([b, d, c], -1)], axis=1).reshape(-1, 3)
    mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
    mesh.vertex_attributes["_STITCH_ID"] = np.repeat(yarn.stitch_ids, sides).astype(np.float32)
    return mesh


def glb_bytes(yarn: YarnPath, sides: int = 8) -> bytes:
    import trimesh

    return trimesh.exchange.gltf.export_glb(trimesh.Scene(tube_mesh(yarn, sides)))


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
    return {"key": p.key, "stats": p.stats, "stitches": stitches, "rows": rows}

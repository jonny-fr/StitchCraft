"""Surface topology derived from the stitch graph: triangles, hinge edges, holes."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

import numpy as np

from stitchcraft_core.graph import StitchGraph

SMALL_HOLE = 12  # boundary loops up to this many edges count as closed (stuffable)


@dataclass
class Topology:
    faces: np.ndarray  # (F, 3) int
    face_row: np.ndarray  # (F,) row index of the upper (child) side
    hinge_edges: set[tuple[int, int]]  # parent-row edges under BLO/FLO stitches
    boundary_loops: list[list[int]]

    @property
    def closed(self) -> bool:
        return all(len(loop) <= SMALL_HOLE for loop in self.boundary_loops)


def build_topology(g: StitchGraph) -> Topology:
    faces: list[tuple[int, int, int]] = []
    face_row: list[int] = []
    hinges: set[tuple[int, int]] = set()

    def emit(tri: tuple[int, int, int], row_idx: int) -> None:
        if g.rows[row_idx].side < 0:
            tri = (tri[0], tri[2], tri[1])
        faces.append(tri)
        face_row.append(row_idx)

    for a, b in g.row_neighbors():
        na, nb = g.nodes[a], g.nodes[b]
        if not na.parents or not nb.parents:
            continue
        pa, pb = na.parents[-1], nb.parents[0]
        if pa == pb:
            emit((a, b, pa), nb.row)
        else:
            emit((a, b, pb), nb.row)
            emit((a, pb, pa), nb.row)
            if na.loop != "both" and nb.loop != "both":
                hinges.add((min(pa, pb), max(pa, pb)))
    for node in g.nodes:
        for p1, p2 in zip(node.parents, node.parents[1:], strict=False):
            emit((node.id, p2, p1), node.row)
            if node.loop != "both":
                hinges.add((min(p1, p2), max(p1, p2)))

    arr = np.array(faces, dtype=np.int64).reshape(-1, 3)
    return Topology(arr, np.array(face_row, dtype=np.int64), hinges, _boundary_loops(arr))


def _boundary_loops(faces: np.ndarray) -> list[list[int]]:
    half: dict[tuple[int, int], int] = defaultdict(int)
    for f in faces:
        for k in range(3):
            half[(int(f[k]), int(f[(k + 1) % 3]))] += 1
    boundary = {a: b for (a, b), c in half.items() if (b, a) not in half}
    loops: list[list[int]] = []
    seen: set[int] = set()
    for start in sorted(boundary):
        if start in seen:
            continue
        loop = [start]
        seen.add(start)
        nxt = boundary.get(start)
        while nxt is not None and nxt != start and nxt not in seen:
            loop.append(nxt)
            seen.add(nxt)
            nxt = boundary.get(nxt)
        loops.append(loop)
    return loops


def cap_faces(topo: Topology) -> np.ndarray:
    """Fan triangles closing small holes, oriented consistently with the surface."""
    caps = []
    for loop in topo.boundary_loops:
        if len(loop) > SMALL_HOLE or len(loop) < 3:
            continue
        # boundary half-edges run a->b; the cap must use b->a
        for k in range(1, len(loop) - 1):
            caps.append((loop[0], loop[k + 1], loop[k]))
    return np.array(caps, dtype=np.int64).reshape(-1, 3)


def bending_quads(faces: np.ndarray) -> np.ndarray:
    """(E, 4) rows (i, j, k, l): edge i-j shared by triangles (i, j, k) and (j, i, l)."""
    opposite: dict[tuple[int, int], int] = {}
    for f in faces:
        for k in range(3):
            a, b, c = int(f[k]), int(f[(k + 1) % 3]), int(f[(k + 2) % 3])
            opposite[(a, b)] = c
    quads = []
    for (a, b), c in opposite.items():
        if a < b and (b, a) in opposite:
            quads.append((a, b, c, opposite[(b, a)]))
    return np.array(quads, dtype=np.int64).reshape(-1, 4)


def vertex_normals(positions: np.ndarray, faces: np.ndarray) -> np.ndarray:
    v0, v1, v2 = (positions[faces[:, k]] for k in range(3))
    fn = np.cross(v1 - v0, v2 - v0)
    normals = np.zeros_like(positions)
    for k in range(3):
        for axis in range(3):
            normals[:, axis] += np.bincount(
                faces[:, k], weights=fn[:, axis], minlength=len(positions)
            )
    length = np.linalg.norm(normals, axis=1, keepdims=True)
    return np.divide(normals, length, out=np.zeros_like(normals), where=length > 1e-12)

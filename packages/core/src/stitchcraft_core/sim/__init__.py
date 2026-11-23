"""Shape relaxation: one particle per stitch, XPBD constraints derived from the stitch graph."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import scipy.sparse as sp

from stitchcraft_core.graph import StitchGraph
from stitchcraft_core.params import Params
from stitchcraft_core.sim.topology import (
    Topology,
    bending_quads,
    build_topology,
    cap_faces,
    vertex_normals,
)
from stitchcraft_core.sim.xpbd import (
    Collision,
    DihedralGroup,
    DistanceGroup,
    Solver,
    VolumeConstraint,
    dihedral_angle_and_grad,
)

# XPBD compliances; with dt = 1/60 a value of ~3e-4 is "soft" (alpha / dt^2 ~ 1).
STRETCH_COMPLIANCE = 1e-8  # the V-top chain along the row barely stretches
POST_COMPLIANCE = 3e-4  # the stitch post (parent link) gives a little under stuffing
COMPRESS_COMPLIANCE = 1e-3  # but fabric bunches up easily along the row
SHEAR_COMPLIANCE = 1e-4
BEND_COMPLIANCE = 1e-3
HINGE_COMPLIANCE = 5e-3
HINGE_ANGLE = np.radians(90.0)
VOLUME_COMPLIANCE = 1e-2
RING_RADIUS = 1.0  # x row height: centre of the magic ring to the top of round 1
TURNING_CHAIN_OFFSET = 0.9  # x stitch width: a stacked turning chain stands outside the edge


@dataclass
class Shape:
    positions: np.ndarray  # (N, 3) mm, one per graph node
    normals: np.ndarray  # (N, 3) towards the front (right side)
    u: np.ndarray  # working direction
    v: np.ndarray  # from base (parents) to the top of the stitch
    n: np.ndarray  # towards the worker while the stitch was made
    widths: np.ndarray
    heights: np.ndarray
    faces: np.ndarray
    closed: bool
    steps: int


def relax(g: StitchGraph, params: Params, max_steps: int = 300) -> Shape:
    rng = np.random.default_rng(params.seed)
    n_nodes = len(g.nodes)
    sizes = np.array([params.stitch_size(node.type) for node in g.nodes]).reshape(-1, 2)
    widths, heights = sizes[:, 0], sizes[:, 1]

    topo = build_topology(g)
    ideal = _initial_positions(g, params, widths, heights)
    x = ideal + rng.normal(scale=0.02 * params.stitch_width_mm, size=ideal.shape)
    faces = _orient(g, topo, x)

    groups, edges = _distance_groups(g, widths, heights, faces, ideal)
    bend = _bending_group(faces, topo, x)
    groups.append(bend)
    edges |= {(int(min(a, b)), int(max(a, b))) for a, b in bend.quads[:, 2:]}

    sim_mask = np.array([not node.turning for node in g.nodes])
    w_unit = params.stitch_width_mm
    volume = None
    closed = topo.closed and g.ring is not None and len(topo.boundary_loops) > 0
    if closed and params.fill > 0:
        all_faces = np.vstack([faces, cap_faces(topo)])
        volume = VolumeConstraint(all_faces, 0.0, VOLUME_COMPLIANCE)
        if volume.volume(x) < 0:
            all_faces = all_faces[:, [0, 2, 1]]
            volume = VolumeConstraint(all_faces, 0.0, VOLUME_COMPLIANCE)
        volume.target = _stuffed_volume(x, all_faces, params.fill)

    collision = Collision(0.75 * w_unit, _excluded_pairs(n_nodes, edges), compliance=1e-6)
    solver = Solver(x, groups, volume=volume, collision=collision)
    solver.w = sim_mask.astype(float)
    steps = solver.run(max_steps, tol=1e-4 * w_unit)

    x = solver.x
    _place_turning_chains(g, x)
    normals = vertex_normals(x, faces)
    u, v, nn = _frames(g, x, normals, params)
    return Shape(x, normals, u, v, nn, widths, heights, faces, closed, steps)


# --- initial layout -------------------------------------------------------------------------


def _initial_positions(g, params, widths, heights) -> np.ndarray:
    if any(r.kind == "round" for r in g.rows):
        return _profile_layout(g, params, widths, heights)
    return _flat_layout(g, widths, heights)


def _profile_layout(g, params, widths, heights) -> np.ndarray:
    """Rounds on a rotational profile: each round's radius follows its circumference and
    the step between rounds is one stitch height (a growing cone; flat where it can be)."""
    x = np.zeros((len(g.nodes), 3))
    theta = np.full(len(g.nodes), np.nan)
    direction = -1.0 if params.handedness == "right" else 1.0
    r_prev, z_prev = 0.0, 0.0
    for row in g.rows:
        ids = [n for n in row.node_ids if not g.nodes[n].turning]
        if not ids:
            continue
        count = len(ids)
        h = float(np.mean(heights[ids]))
        target = float(widths[ids].sum()) / (2 * np.pi)
        if r_prev == 0.0:
            h *= RING_RADIUS
        dr = float(np.clip(target - r_prev, -h, h))
        dz = float(np.sqrt(max(h * h - dr * dr, 0.0)))
        r = r_prev + dr
        base = direction * 2 * np.pi * (np.arange(count) + 0.5) / count
        parent_theta = np.array([_circmean(theta[g.nodes[n].parents]) for n in ids])
        valid = ~np.isnan(parent_theta)
        offset = _circmean(parent_theta[valid] - base[valid]) if valid.any() else 0.0
        offset = 0.0 if np.isnan(offset) else offset
        ang = base + offset
        excess = max(target / max(r, 1e-9) - 1.0, 0.0)
        wave = 0.6 * h * min(excess, 1.0) * np.sin(max(2, count // 8) * ang)
        for k, n in enumerate(ids):
            theta[n] = ang[k]
            x[n] = (r * np.cos(ang[k]), r * np.sin(ang[k]), z_prev + dz + wave[k])
        r_prev, z_prev = r, z_prev + dz
    return x


def _circmean(a: np.ndarray) -> float:
    a = a[~np.isnan(a)]
    if len(a) == 0:
        return float("nan")
    return float(np.arctan2(np.sin(a).mean(), np.cos(a).mean()))


def _flat_layout(g, widths, heights) -> np.ndarray:
    x = np.zeros((len(g.nodes), 3))
    cursor = 0.0
    for row in g.rows:
        siblings: dict[int, int] = {}
        for n in row.node_ids:
            node = g.nodes[n]
            if node.turning:
                continue
            if node.parents:
                px = x[node.parents]
                k = siblings.get(node.parents[0], 0)
                siblings[node.parents[0]] = k + 1
                x[n] = (px[:, 0].mean() + 0.3 * k * widths[n], px[:, 1].max() + heights[n], 0)
            else:
                x[n] = (cursor, 0.0, 0.0)
                cursor += widths[n]
    return x


def _orient(g: StitchGraph, topo: Topology, x: np.ndarray) -> np.ndarray:
    """Flip all faces so normals point to the right side: away from the growth direction
    at the start of rounds, +z for flat rows."""
    faces = topo.faces
    if len(faces) == 0:
        return faces
    fn = np.cross(x[faces[:, 1]] - x[faces[:, 0]], x[faces[:, 2]] - x[faces[:, 0]])
    first = topo.face_row == topo.face_row.min()
    want = -1.0 if g.rows[0].kind == "round" else 1.0
    if np.sign(fn[first, 2].sum()) != want:
        faces = faces[:, [0, 2, 1]]
    topo.faces = faces
    return faces


# --- constraints ----------------------------------------------------------------------------


def _distance_groups(g, widths, heights, faces, ideal):
    edges: set[tuple[int, int]] = set()
    si, sj, srest = [], [], []
    for a, b in g.row_neighbors():
        si.append(a)
        sj.append(b)
        rest = 0.5 * (widths[a] + widths[b])
        if g.nodes[a].row != g.nodes[b].row:
            # spiral seam: the yarn climbs one stitch height (the visible jog)
            rest = float(np.hypot(rest, heights[b]))
        srest.append(rest)
    pi, pj, prest = [], [], []
    for node in g.nodes:
        if node.turning:
            continue
        for p in node.parents:
            h = heights[node.id]
            if g.nodes[p].type == "ring":
                h *= RING_RADIUS
            elif len(node.parents) > 1:
                h = float(np.hypot(h, 0.5 * widths[node.id]))
            pi.append(node.id)
            pj.append(p)
            prest.append(h)
    stretch = DistanceGroup(
        np.array(si + pi, dtype=np.int64),
        np.array(sj + pj, dtype=np.int64),
        np.array(srest + prest, dtype=float),
        np.array([STRETCH_COMPLIANCE] * len(si) + [POST_COMPLIANCE] * len(pi)),
        compress_compliance=np.array(
            [COMPRESS_COMPLIANCE] * len(si) + [STRETCH_COMPLIANCE] * len(pi)
        ),
    )
    edges |= {(min(a, b), max(a, b)) for a, b in zip(stretch.i, stretch.j, strict=True)}

    # shear: the remaining triangle edges (quad diagonals, dec spans)
    di, dj = [], []
    for f in faces:
        for k in range(3):
            a, b = int(f[k]), int(f[(k + 1) % 3])
            key = (min(a, b), max(a, b))
            if key not in edges:
                edges.add(key)
                di.append(key[0])
                dj.append(key[1])
    shear = DistanceGroup(
        np.array(di, dtype=np.int64),
        np.array(dj, dtype=np.int64),
        np.linalg.norm(ideal[di] - ideal[dj], axis=1).reshape(-1),
        np.asarray(SHEAR_COMPLIANCE),
        compress_compliance=np.asarray(COMPRESS_COMPLIANCE),
    )
    return [stretch, shear], edges


def _bending_group(faces, topo: Topology, x) -> DihedralGroup:
    """Fabric is flat at rest; BLO/FLO edges act as hinges with a preferred fold."""
    quads = bending_quads(faces)
    if len(quads) == 0:
        return DihedralGroup(np.zeros((0, 4), dtype=np.int64), np.zeros(0), np.asarray(0.0))
    hinge = np.array(
        [(min(a, b), max(a, b)) in topo.hinge_edges for a, b in quads[:, :2]], dtype=bool
    )
    theta0, _ = dihedral_angle_and_grad(x, quads)
    direction = np.where(theta0 < 0, -1.0, 1.0)
    rest = np.where(hinge, direction * HINGE_ANGLE, 0.0)
    compliance = np.where(hinge, HINGE_COMPLIANCE, BEND_COMPLIANCE)
    return DihedralGroup(quads, rest, compliance)


def _stuffed_volume(x, faces, fill: float) -> float:
    a, b, c = (x[faces[:, k]] for k in range(3))
    area = 0.5 * np.linalg.norm(np.cross(b - a, c - a), axis=1).sum()
    sphere_max = area**1.5 / (6 * np.sqrt(np.pi))
    return float(sphere_max * (0.9 + 0.2 * fill))


def _excluded_pairs(n: int, edges: set[tuple[int, int]]) -> np.ndarray:
    if not edges:
        return np.zeros(0, dtype=np.int64)
    a = np.array([e[0] for e in edges])
    b = np.array([e[1] for e in edges])
    adj = sp.coo_matrix((np.ones(len(a)), (a, b)), shape=(n, n)).tocsr()
    adj = adj + adj.T
    near = (adj + adj @ adj).tocoo()
    keep = near.row < near.col
    return np.unique(near.row[keep].astype(np.int64) * n + near.col[keep])


# --- post-processing ------------------------------------------------------------------------


def _place_turning_chains(g: StitchGraph, x: np.ndarray) -> None:
    order = [n for n in range(len(g.nodes)) if g.nodes[n].type != "ring"]
    real = [n for n in order if not g.nodes[n].turning]
    runs: list[list[int]] = []
    for k, n in enumerate(order):
        if g.nodes[n].turning:
            if k and g.nodes[order[k - 1]].turning:
                runs[-1].append(n)
            else:
                runs.append([n])
    for run in runs:
        before = [m for m in real if m < run[0]]
        after = [m for m in real if m > run[-1]]
        if len(run) > 1 and before and after:
            _stack_turning_chain(g, x, run, before[-1], after)
            continue
        for n in run:
            if before and after:
                x[n] = 0.5 * (x[before[-1]] + x[after[0]])
            elif before:
                x[n] = x[before[-1]]


def _stack_turning_chain(g: StitchGraph, x, run: list[int], below: int, after: list[int]):
    """A turning chain of several stitches climbs the edge from the last stitch to the
    first of the next row, standing beside that stitch on the outside, not on its post."""
    first = after[0]
    climb = x[first] - x[below]
    out = np.zeros(3)
    if len(after) > 1 and g.nodes[after[1]].row == g.nodes[first].row:
        step = x[first] - x[after[1]]  # one stitch width, pointing out of the edge
        side = step - (step @ climb) / max(climb @ climb, 1e-12) * climb
        out = TURNING_CHAIN_OFFSET * np.linalg.norm(step) * side / max(np.linalg.norm(side), 1e-9)
    for j, n in enumerate(run, start=1):
        x[n] = x[below] + j / (len(run) + 1) * climb + out


def _any_perpendicular(a: np.ndarray) -> np.ndarray:
    helper = np.array([1.0, 0.0, 0.0]) if abs(a[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    return np.cross(a, helper)


def _frames(g: StitchGraph, x, normals, params: Params):
    n_nodes = len(g.nodes)
    u = np.zeros((n_nodes, 3))
    v = np.zeros((n_nodes, 3))
    nn = np.zeros((n_nodes, 3))
    sign_out = 1.0 if params.right_side_out else -1.0
    order = [i for i in range(n_nodes) if g.nodes[i].type != "ring"]
    children: dict[int, list[int]] = {}
    for node in g.nodes:
        for p in node.parents:
            children.setdefault(p, []).append(node.id)
    for k, i in enumerate(order):
        node = g.nodes[i]
        side = g.rows[node.row].side if node.row >= 0 else 1
        normal = normals[i] if np.linalg.norm(normals[i]) > 0 else np.array([0.0, 0.0, 1.0])
        front = normal * side * sign_out
        prev_i = order[k - 1] if k > 0 else i
        next_i = order[k + 1] if k + 1 < len(order) else i
        tangent = x[next_i] - x[prev_i]
        if node.parents:
            up = x[i] - x[node.parents].mean(axis=0)
        elif i in children:
            up = x[children[i]].mean(axis=0) - x[i]
        else:
            up = np.cross(front, tangent)
        front = front / np.linalg.norm(front)
        up = up - (up @ front) * front
        if np.linalg.norm(up) < 1e-9:
            up = np.cross(front, tangent)
        if np.linalg.norm(up) < 1e-9:
            up = _any_perpendicular(front)
        up /= np.linalg.norm(up)
        tan = tangent - (tangent @ front) * front - (tangent @ up) * up
        if np.linalg.norm(tan) < 1e-9:
            tan = np.cross(up, front)
        tan /= np.linalg.norm(tan)
        u[i], v[i], nn[i] = tan, up, front
    if g.ring is not None:
        u[g.ring], v[g.ring], nn[g.ring] = (1, 0, 0), (0, 1, 0), (0, 0, 1)
    return u, v, nn

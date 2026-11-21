"""Yarn placement: stitch templates in the relaxed surface frames, joined into one
continuous centre line (C1 Catmull-Rom), then a few rounds of contact relaxation."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree

from stitchcraft_core.graph import StitchGraph
from stitchcraft_core.params import Params
from stitchcraft_core.sim import Shape
from stitchcraft_core.yarn.templates import template_for

SAMPLE_SPACING = 0.5  # x yarn radius
RING_RADIUS = 3.0  # x yarn radius
CONTACT_ITERATIONS = 60
ANCHOR_STIFFNESS = 0.002
FINAL_SPACING_SWEEPS = 30
AFFECTED_DEPTH = 0.02  # x yarn radius: below this a contact counts as touching, not penetrating
EXCLUDE_ARC = 4.0  # x yarn radius: neighbours along the yarn closer than this never collide


@dataclass
class YarnPath:
    points: np.ndarray  # (M, 3) float
    radius: np.ndarray  # (M,)
    stitch_ids: np.ndarray  # (M,) int
    segment_offsets: np.ndarray  # start index of each continuous strand
    max_step: float  # largest sample spacing produced by the spline sampling
    yarn_radius: float


def build_yarn(g: StitchGraph, shape: Shape, params: Params) -> YarnPath:
    r = params.yarn_radius_mm
    ctrl, owners = _control_points(g, shape, r)
    points, ids = _sample(ctrl, owners, SAMPLE_SPACING * r)
    max_step = float(np.linalg.norm(np.diff(points, axis=0), axis=1).max())
    points = relax_contacts(points, r)
    return YarnPath(
        points=points,
        radius=np.full(len(points), r),
        stitch_ids=ids,
        segment_offsets=np.array([0], dtype=np.int64),
        max_step=max_step,
        yarn_radius=r,
    )


# --- control points -------------------------------------------------------------------------


def _template_name(node) -> str:
    if node.type in ("ch", "slst"):
        return node.type
    if node.op == "dec":
        return "dec"
    return "sc"  # hdc/dc/tr templates follow in M5; until then they use the sc shape stretched


def _local_width(g: StitchGraph, shape: Shape, order: list[int], k: int) -> float:
    i = order[k]
    nominal = float(shape.widths[i])
    spans = []
    for j in (k - 1, k + 1):
        if 0 <= j < len(order) and g.nodes[order[j]].row == g.nodes[i].row:
            spans.append(float(np.linalg.norm(shape.positions[order[j]] - shape.positions[i])))
    if not spans:
        return nominal
    return float(np.clip(np.mean(spans), 0.5 * nominal, 1.5 * nominal))


def _control_points(g: StitchGraph, shape: Shape, r: float):
    x = shape.positions
    order = [n.id for n in g.nodes if n.type != "ring"]
    ctrl: list[np.ndarray] = []
    owners: list[int] = []

    ring_centre = x[g.ring] if g.ring is not None else None
    ring_axis = None
    if g.ring is not None:
        first_round = [n for n in g.rows[0].node_ids if not g.nodes[n].turning]
        ring_axis = shape.normals[first_round].mean(axis=0)
        ring_axis /= np.linalg.norm(ring_axis)
        ctrl.extend(_ring_loop(ring_centre, ring_axis, x[first_round[0]], RING_RADIUS * r))
        owners.extend([g.ring] * (len(ctrl)))

    for k, i in enumerate(order):
        node = g.nodes[i]
        tpl = template_for(_template_name(node), node.loop)
        u, v, n = shape.u[i], shape.v[i], shape.n[i]
        w = _local_width(g, shape, order, k)
        if node.type == "ch":
            h = float(shape.heights[i])
            base = x[i] - 0.5 * h * v
        elif node.parents and g.nodes[node.parents[0]].type == "ring":
            radial = x[i] - ring_centre
            radial -= (radial @ ring_axis) * ring_axis
            radial /= max(np.linalg.norm(radial), 1e-9)
            # the legs pass through the ring, just inside the ring yarn
            h = float(np.linalg.norm(x[i] - ring_centre)) - (RING_RADIUS - 2.0) * r
            base = x[i] - h * radial
        else:
            h = float(np.linalg.norm(x[i] - x[node.parents].mean(axis=0))) if node.parents else 0.0
            h = h or float(shape.heights[i])
            base = x[i] - h * v
        bases = [base]
        bases += [x[p] for p in node.parents[:2]] if node.parents else []
        pts = []
        for (pu, pv, pn), anchor in zip(tpl.points, tpl.anchors, strict=True):
            b = bases[anchor] if anchor < len(bases) else base
            pts.append(b + pu * w * u + pv * h * v + pn * r * n)
        if ctrl:
            ctrl[-1] = 0.5 * (ctrl[-1] + pts[0])
            owners[-1] = i
            ctrl.extend(pts[1:])
            owners.extend([i] * (len(pts) - 1))
        else:
            ctrl.extend(pts)
            owners.extend([i] * len(pts))
    return np.array(ctrl), np.array(owners, dtype=np.int64)


def _ring_loop(centre, axis, first_top, radius) -> list[np.ndarray]:
    ref = first_top - centre
    ref -= (ref @ axis) * axis
    ref /= max(np.linalg.norm(ref), 1e-9)
    side = np.cross(axis, ref)
    angles = np.linspace(-2.25 * np.pi, 0.0, 12)
    return [centre + radius * (np.cos(a) * ref + np.sin(a) * side) for a in angles]


# --- spline sampling ------------------------------------------------------------------------


def _sample(ctrl: np.ndarray, owners: np.ndarray, spacing: float):
    """Centripetal Catmull-Rom through all control points, resampled to uniform arc length."""
    p = np.vstack([2 * ctrl[0] - ctrl[1], ctrl, 2 * ctrl[-1] - ctrl[-2]])
    dense_pts = []
    dense_ids = []
    for s in range(len(ctrl) - 1):
        seg = np.linalg.norm(p[s + 2] - p[s + 1])
        count = max(4, int(np.ceil(4 * seg / spacing)))
        t = np.arange(count) / count
        dense_pts.append(_catmull_rom(p[s], p[s + 1], p[s + 2], p[s + 3], t))
        dense_ids.append(np.full(count, owners[s + 1]))
    dense_pts.append(ctrl[-1][None])
    dense_ids.append(owners[-1:])
    dense = np.vstack(dense_pts)
    ids = np.concatenate(dense_ids)
    arc = np.concatenate([[0.0], np.cumsum(np.linalg.norm(np.diff(dense, axis=0), axis=1))])
    n = max(2, int(np.ceil(arc[-1] / spacing)) + 1)
    targets = np.linspace(0.0, arc[-1], n)
    out = np.column_stack([np.interp(targets, arc, dense[:, k]) for k in range(3)])
    nearest = np.clip(np.searchsorted(arc, targets), 0, len(ids) - 1)
    return out, ids[nearest]


def _catmull_rom(p0, p1, p2, p3, t, alpha: float = 0.5) -> np.ndarray:
    def knot(a, b, ti):
        return ti + max(float(np.linalg.norm(b - a)) ** alpha, 1e-9)

    t0 = 0.0
    t1 = knot(p0, p1, t0)
    t2 = knot(p1, p2, t1)
    t3 = knot(p2, p3, t2)
    tt = (t1 + (t2 - t1) * t)[:, None]
    a1 = (t1 - tt) / (t1 - t0) * p0 + (tt - t0) / (t1 - t0) * p1
    a2 = (t2 - tt) / (t2 - t1) * p1 + (tt - t1) / (t2 - t1) * p2
    a3 = (t3 - tt) / (t3 - t2) * p2 + (tt - t2) / (t3 - t2) * p3
    b1 = (t2 - tt) / (t2 - t0) * a1 + (tt - t0) / (t2 - t0) * a2
    b2 = (t3 - tt) / (t3 - t1) * a2 + (tt - t1) / (t3 - t1) * a3
    return (t2 - tt) / (t2 - t1) * b1 + (tt - t1) / (t2 - t1) * b2


# --- contact relaxation ---------------------------------------------------------------------


def _window(points: np.ndarray, r: float) -> int:
    step = float(np.median(np.linalg.norm(np.diff(points, axis=0), axis=1)))
    return int(np.ceil(EXCLUDE_ARC * r / max(step, 1e-9)))


def relax_contacts(points: np.ndarray, r: float, iterations: int = CONTACT_ITERATIONS):
    """Push apart yarn samples closer than one yarn diameter while keeping the spacing along
    the yarn. Templates are designed nearly contact-free, so this only polishes and must not
    change which strand passes over which."""
    p = points.copy()
    anchor = points.copy()
    rest = np.linalg.norm(np.diff(points, axis=0), axis=1)
    window = _window(points, r)
    n = len(p)
    for _ in range(iterations):
        p += ANCHOR_STIFFNESS * (anchor - p)
        pairs = cKDTree(p).query_pairs(2 * r, output_type="ndarray")
        if len(pairs):
            pairs = pairs[np.abs(pairs[:, 0] - pairs[:, 1]) > window]
        if len(pairs):
            d = p[pairs[:, 0]] - p[pairs[:, 1]]
            length = np.maximum(np.linalg.norm(d, axis=1), 1e-9)
            corr = (0.5 * (2 * r - length) / length)[:, None] * d
            acc = np.zeros_like(p)
            np.add.at(acc, pairs[:, 0], corr)
            np.add.at(acc, pairs[:, 1], -corr)
            count = np.bincount(pairs.ravel(), minlength=n)
            p += acc / np.sqrt(np.maximum(count, 1))[:, None]
        for _ in range(3):
            _keep_spacing(p, rest)
    for _ in range(FINAL_SPACING_SWEEPS):
        _keep_spacing(p, rest)
    return p


def _keep_spacing(p: np.ndarray, rest: np.ndarray) -> None:
    d = p[1:] - p[:-1]
    length = np.maximum(np.linalg.norm(d, axis=1), 1e-9)
    corr = (0.5 * (length - rest) / length)[:, None] * d
    acc = np.zeros_like(p)
    acc[:-1] += corr
    acc[1:] -= corr
    count = np.full(len(p), 2.0)
    count[[0, -1]] = 1.0
    p += acc / count[:, None]


# --- evaluation (A5) ------------------------------------------------------------------------


@dataclass
class PenetrationStats:
    max_depth: float
    affected_fraction: float
    pairs: int


def penetration_stats(yarn: YarnPath) -> PenetrationStats:
    """Capsule-capsule penetration between non-neighbouring yarn segments."""
    p = yarn.points
    r = yarn.yarn_radius
    a, b = p[:-1], p[1:]
    mid = 0.5 * (a + b)
    seg_max = float(np.linalg.norm(b - a, axis=1).max())
    pairs = cKDTree(mid).query_pairs(2 * r + seg_max, output_type="ndarray")
    window = _window(p, r)
    if len(pairs):
        pairs = pairs[np.abs(pairs[:, 0] - pairs[:, 1]) > window]
    if len(pairs) == 0:
        return PenetrationStats(0.0, 0.0, 0)
    d = segment_distances(a[pairs[:, 0]], b[pairs[:, 0]], a[pairs[:, 1]], b[pairs[:, 1]])
    depth = np.maximum(2 * r - d, 0.0)
    return PenetrationStats(
        max_depth=float(depth.max()),
        affected_fraction=float((depth > AFFECTED_DEPTH * r).mean()),
        pairs=len(pairs),
    )


def segment_distances(p1, q1, p2, q2) -> np.ndarray:
    """Minimum distances between segment pairs p1-q1 and p2-q2 (vectorised, Ericson 5.1.9)."""
    d1 = q1 - p1
    d2 = q2 - p2
    r = p1 - p2
    a = np.einsum("ij,ij->i", d1, d1)
    e = np.einsum("ij,ij->i", d2, d2)
    f = np.einsum("ij,ij->i", d2, r)
    c = np.einsum("ij,ij->i", d1, r)
    b = np.einsum("ij,ij->i", d1, d2)
    denom = a * e - b * b
    s = np.where(denom > 1e-12, np.clip((b * f - c * e) / np.maximum(denom, 1e-12), 0, 1), 0.0)
    t = (b * s + f) / np.maximum(e, 1e-12)
    s = np.where(t < 0, np.clip(-c / np.maximum(a, 1e-12), 0, 1), s)
    s = np.where(t > 1, np.clip((b - c) / np.maximum(a, 1e-12), 0, 1), s)
    t = np.clip(t, 0, 1)
    c1 = p1 + d1 * s[:, None]
    c2 = p2 + d2 * t[:, None]
    return np.linalg.norm(c1 - c2, axis=1)

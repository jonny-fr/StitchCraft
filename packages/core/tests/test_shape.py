import hashlib

import numpy as np
import pytest
from conftest import reference_pattern
from stitchcraft_core.params import Params
from stitchcraft_core.sim import relax
from stitchcraft_core.validate import validate

P = Params()


@pytest.fixture(scope="module")
def shapes():
    cache = {}

    def get(piece, params=P):
        key = (piece, params)
        if key not in cache:
            g = validate(reference_pattern(piece)).graph
            cache[key] = (g, relax(g, params))
        return cache[key]

    return get


def plane_fit(points):
    c = points.mean(axis=0)
    _, _, vt = np.linalg.svd(points - c)
    return c, vt[2]


def round_stats(g, shape, axis_origin, axis):
    out = {}
    for row in g.rows:
        pts = shape.positions[g.counting_ids(row)]
        rel = pts - axis_origin
        h = rel @ axis
        radial = rel - np.outer(h, axis)
        out[row.number] = (h.mean(), np.linalg.norm(radial, axis=1).mean())
    return out


def test_square_dimensions_follow_gauge(shapes):
    g, s = shapes("1-square")
    pts = s.positions[[n.id for n in g.nodes if n.counting]]
    c, normal = plane_fit(pts)
    rel = pts - c
    row = g.counting_ids(g.rows[5])
    along = s.positions[row[-1]] - s.positions[row[0]]
    along -= (along @ normal) * normal
    along /= np.linalg.norm(along)
    across = np.cross(normal, along)
    w, h = P.stitch_width_mm, P.row_height_mm
    # 15 stitches wide; 15 sc rows plus the foundation chain tall (node centres)
    assert np.ptp(rel @ along) == pytest.approx(14 * w, rel=0.10)
    assert np.ptp(rel @ across) == pytest.approx(15 * h, rel=0.10)
    assert np.ptp(rel @ normal) < 0.5 * h


def test_disc_stays_flat(shapes):
    g, s = shapes("2-disc")
    pts = s.positions[[n.id for n in g.nodes if n.counting]]
    _, normal = plane_fit(pts)
    flatness = np.ptp((pts - pts.mean(0)) @ normal)
    diameter = np.ptp(pts, axis=0).max()
    # not an A7 criterion: with h/w = 1 six increases per round give a very shallow cone
    assert flatness < 0.15 * diameter


def test_sphere_aspect_ratio(shapes):
    """A7: stuffed ball height/width within 0.9-1.1."""
    g, s = shapes("3-sphere")
    pts = s.positions[[n.id for n in g.nodes if n.counting]]
    first = s.positions[g.counting_ids(g.rows[0])].mean(0)
    last = s.positions[g.counting_ids(g.rows[-1])].mean(0)
    axis = (last - first) / np.linalg.norm(last - first)
    rel = pts - pts.mean(0)
    height = np.ptp(rel @ axis)
    radial = rel - np.outer(rel @ axis, axis)
    width = 2 * np.linalg.norm(radial, axis=1).max()
    assert 0.9 <= height / width <= 1.1, (height, width)


def test_cup_wall_rises_at_right_angle(shapes):
    """A7: bottom-wall angle 75-105 degrees."""
    g, s = shapes("4-cup")
    base = s.positions[[n for r in g.rows[:5] for n in g.counting_ids(r)]]
    c, normal = plane_fit(base)
    wall = s.positions[g.counting_ids(g.rows[-1])].mean(0)
    if (wall - c) @ normal < 0:
        normal = -normal
    stats = round_stats(g, s, c, normal)
    h6, r6 = stats[6]
    h16, r16 = stats[16]
    angle = np.degrees(np.arctan2(h16 - h6, r16 - r6))
    assert 75 <= angle <= 105, angle


def test_hyperbolic_disc_ruffles(shapes):
    """A7: hyperbolic disc is not planar."""
    g, s = shapes("5-hyperbolic")
    outer = s.positions[g.counting_ids(g.rows[-1])]
    _, normal = plane_fit(outer)
    deviation = (outer - outer.mean(0)) @ normal
    assert deviation.std() > 0.5 * P.row_height_mm


def test_hyperbolic_disc_has_no_node_overlap(shapes):
    g, s = shapes("5-hyperbolic")
    from scipy.spatial import cKDTree

    pts = s.positions[[n.id for n in g.nodes if n.counting]]
    d, _ = cKDTree(pts).query(pts, k=2)
    assert d[:, 1].min() > 0.4 * P.stitch_width_mm


def test_spiral_jog_is_visible(shapes):
    """A7: at the spiral seam the yarn steps up by about one row height."""
    g, s = shapes("4-cup")
    base = s.positions[[n for r in g.rows[:5] for n in g.counting_ids(r)]]
    c, normal = plane_fit(base)
    if (s.positions[g.counting_ids(g.rows[-1])].mean(0) - c) @ normal < 0:
        normal = -normal
    last_of_round = g.counting_ids(g.rows[9])[-1]
    first_of_next = g.counting_ids(g.rows[10])[0]
    step = (s.positions[first_of_next] - s.positions[last_of_round]) @ normal
    assert step > 0.5 * P.row_height_mm


def test_relax_is_deterministic():
    """A8: same input + seed -> identical result."""
    g = validate(reference_pattern("2-disc")).graph
    a = relax(g, P).positions
    b = relax(g, P).positions
    assert hashlib.sha256(a.tobytes()).digest() == hashlib.sha256(b.tobytes()).digest()


def test_frames_are_orthonormal(shapes):
    g, s = shapes("3-sphere")
    for axis in (s.u, s.v, s.n):
        assert np.allclose(np.linalg.norm(axis, axis=1), 1.0, atol=1e-6)
    assert np.all(np.abs(np.einsum("ij,ij->i", s.u, s.n)) < 1e-6)


def test_normals_point_outward_on_sphere(shapes):
    g, s = shapes("3-sphere")
    ids = [n.id for n in g.nodes if n.counting]
    centre = s.positions[ids].mean(0)
    outward = np.einsum("ij,ij->i", s.normals[ids], s.positions[ids] - centre)
    assert (outward > 0).mean() > 0.95

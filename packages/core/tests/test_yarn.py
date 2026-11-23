import hashlib

import numpy as np
import pytest
from conftest import reference_pattern
from stitchcraft_core.params import Params
from stitchcraft_core.sim import relax
from stitchcraft_core.validate import validate
from stitchcraft_core.yarn import build_yarn, penetration_stats

P = Params()


@pytest.fixture(scope="module")
def yarns():
    cache = {}

    def get(piece):
        if piece not in cache:
            g = validate(reference_pattern(piece)).graph
            cache[piece] = (g, build_yarn(g, relax(g, P), P))
        return cache[piece]

    return get


@pytest.mark.parametrize("piece", ["1-square", "3-sphere", "4-cup"])
def test_yarn_is_one_continuous_curve(yarns, piece):
    """A4: one connected curve per part; where one stitch's yarn hands over to the next
    there is no jump beyond the normal sample spacing on either side."""
    _, y = yarns(piece)
    assert len(y.segment_offsets) == 1
    steps = np.linalg.norm(np.diff(y.points, axis=0), axis=1)
    boundaries = np.flatnonzero(np.diff(y.stitch_ids) != 0)
    inner = boundaries[(boundaries > 0) & (boundaries < len(steps) - 1)]
    around = np.maximum(steps[inner - 1], steps[inner + 1])
    gap = (steps[inner] - around).max()
    assert gap <= 0.05 * P.yarn_radius_mm
    assert steps.max() < P.yarn_radius_mm


@pytest.mark.parametrize("piece", ["1-square", "2-disc", "3-sphere", "4-cup", "5-hyperbolic"])
def test_no_yarn_penetration_after_contact_relaxation(yarns, piece):
    """A5: max penetration <= 10 % of the yarn radius, <= 1 % of segment pairs affected."""
    _, y = yarns(piece)
    stats = penetration_stats(y)
    assert stats.max_depth <= 0.10 * P.yarn_radius_mm, stats
    assert stats.affected_fraction <= 0.01, stats


def test_every_stitch_owns_yarn(yarns):
    g, y = yarns("3-sphere")
    owners = set(np.unique(y.stitch_ids).tolist())
    assert {n.id for n in g.nodes if n.type != "ring"} <= owners


def test_yarn_of_a_stitch_reaches_into_its_parent(yarns):
    """The pulled-up loop passes through the parent's top: some of its yarn lies close
    to the parent's top, closer than half a row height."""
    g, y = yarns("2-disc")
    from stitchcraft_core.sim import relax as _relax

    shape = _relax(g, P)
    for node in g.nodes:
        if node.type != "sc" or not node.parents or g.nodes[node.parents[0]].type == "ring":
            continue
        pts = y.points[y.stitch_ids == node.id]
        parent = shape.positions[node.parents[0]]
        assert np.linalg.norm(pts - parent, axis=1).min() < 0.5 * P.row_height_mm


def test_yarn_is_deterministic():
    """A8: same input + seed -> identical yarn path hash."""
    g = validate(reference_pattern("2-disc")).graph
    a = build_yarn(g, relax(g, P), P).points
    b = build_yarn(g, relax(g, P), P).points
    assert hashlib.sha256(a.tobytes()).hexdigest() == hashlib.sha256(b.tobytes()).hexdigest()


def test_back_loop_stitches_use_their_own_template():
    from stitchcraft_core.yarn.templates import template_for

    assert not np.allclose(template_for("sc", "blo").points, template_for("sc", "both").points)
    assert not np.allclose(template_for("sc", "flo").points, template_for("sc", "both").points)


def test_segment_distance_cases():
    from stitchcraft_core.yarn import segment_distances

    p1 = np.array([[0.0, 0, 0], [0, 0, 0], [0, 0, 0]])
    q1 = np.array([[1.0, 0, 0], [1, 0, 0], [1, 0, 0]])
    p2 = np.array([[0.5, -1, 1], [2, 0, 0], [0, 1, 0]])  # crossing above, collinear gap, parallel
    q2 = np.array([[0.5, 1, 1], [3, 0, 0], [1, 1, 0]])
    assert np.allclose(segment_distances(p1, q1, p2, q2), [1.0, 1.0, 1.0])


TALL = ["hdc", "dc", "tr"]


@pytest.mark.parametrize("stitch", TALL)
@pytest.mark.parametrize("loop", ["both", "blo", "flo"])
def test_tall_stitch_templates_load(stitch, loop):
    from stitchcraft_core.yarn.templates import template_for

    tpl = template_for(stitch, loop)
    assert np.allclose(tpl.points[0], [-0.5, 1.0, 0.0])
    assert np.allclose(tpl.points[-1], [0.5, 1.0, 0.0])
    assert not np.array_equal(tpl.points, template_for("sc", loop).points)
    if loop != "both":
        assert not np.array_equal(tpl.points, template_for(stitch, "both").points)


@pytest.mark.parametrize("stitch", TALL)
def test_tall_decrease_templates_pass_through_both_parents(stitch):
    from stitchcraft_core.yarn.templates import template_for

    tpl = template_for(f"{stitch}_dec")
    assert {0, 1, 2} <= set(tpl.anchors.tolist())
    assert not np.array_equal(tpl.points, template_for("dec").points)
    assert not np.array_equal(tpl.points, template_for(stitch).points)


@pytest.mark.parametrize(
    ("stitch", "op", "name"),
    [
        ("sc", None, "sc"),
        ("sc", "inc", "sc"),
        ("sc", "dec", "dec"),
        ("hdc", None, "hdc"),
        ("dc", "inc", "dc"),
        ("tr", None, "tr"),
        ("hdc", "dec", "hdc_dec"),
        ("dc", "dec", "dc_dec"),
        ("tr", "dec", "tr_dec"),
        ("ch", None, "ch"),
        ("slst", None, "slst"),
    ],
)
def test_template_name(stitch, op, name):
    from stitchcraft_core.graph import Node
    from stitchcraft_core.yarn import _template_name

    assert _template_name(Node(id=0, row=0, type=stitch, op=op)) == name


def _turns_around_post(stitch: str, loop: str) -> float:
    """Signed turns of the centre line around the post axis (u = n = 0), seen from the top,
    with u converted from stitch widths to yarn radii like n."""
    from stitchcraft_core.yarn.templates import template_for

    width_r = P.stitch_width_mm / P.yarn_radius_mm
    pts = template_for(stitch, loop).points
    angle = np.arctan2(pts[:, 2], pts[:, 0] * width_r)
    step = (np.diff(angle) + np.pi) % (2 * np.pi) - np.pi
    return float(step.sum() / (2 * np.pi))


@pytest.mark.parametrize(("stitch", "wraps"), [("sc", 0), ("hdc", 1), ("dc", 1), ("tr", 2)])
@pytest.mark.parametrize("loop", ["both", "blo", "flo"])
def test_yarn_overs_wrap_around_the_post(stitch, wraps, loop):
    """Each yarn-over is one full turn around the post. From junction to junction the
    centre line of an sc turns half a turn (in at the left, across the front, out at the
    right); every wrap adds one turn in the same sense."""
    turns = _turns_around_post(stitch, loop)
    assert abs(turns) == pytest.approx(0.5 + wraps, abs=1e-6)


@pytest.mark.slow
@pytest.mark.parametrize("piece", ["hstb-quadrat", "dstb-quadrat", "stb-scheibe", "stb-abnahmen"])
def test_tall_stitch_pieces_continuous_and_without_penetration(piece):
    """A4 and A5 for the hdc/tr squares, dc rounds from a magic ring and dc2tog."""
    from stitchcraft_core.gate import M5_EXTRA

    g = validate(M5_EXTRA[piece], dialect="de").graph
    assert {n.type for n in g.nodes} & {"hdc", "dc", "tr"}
    y = build_yarn(g, relax(g, P), P)
    steps = np.linalg.norm(np.diff(y.points, axis=0), axis=1)
    boundaries = np.flatnonzero(np.diff(y.stitch_ids) != 0)
    inner = boundaries[(boundaries > 0) & (boundaries < len(steps) - 1)]
    gap = (steps[inner] - np.maximum(steps[inner - 1], steps[inner + 1])).max()
    assert gap <= 0.05 * P.yarn_radius_mm
    stats = penetration_stats(y)
    assert stats.max_depth <= 0.10 * P.yarn_radius_mm, stats
    assert stats.affected_fraction <= 0.01, stats

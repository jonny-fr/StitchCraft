"""Generator of the tall-stitch yarn templates (hdc, dc, tr and their decreases).

The shapes are designed in compressed yarn radii (r) and converted to template units; the
result is the generated section at the end of data/stitches/templates.toml. Change the
shapes here, then rewrite that section:

    uv run python -m stitchcraft_core.yarn.design
"""

from __future__ import annotations

from collections.abc import Callable

from stitchcraft_core.data import data_dir

Point = tuple[float, float, float]  # u (stitch widths), v (r above the parent's top), n (r)

W = 5.075 / 0.6  # nominal stitch width = sc height, in r (3.5 mm hook, 2 mm yarn)
B, BN = 1.1, 1.2  # the post: four strands at u = +-B, n = +-BN (r)
# cross-sections of a wrap, every 45 deg clockwise (seen from the top) from the right side
RING4 = [
    (3.3, 0.0),
    (2.9, -3.0),
    (0.0, -3.4),
    (-2.9, -3.0),
    (-3.3, 0.0),
    (-2.9, 3.0),
    (0.0, 3.4),
    (2.9, 3.0),
]
RING2 = [
    (2.3, 0.0),
    (1.8, -2.8),
    (0.0, -3.4),
    (-1.8, -2.8),
    (-2.3, 0.0),
    (-1.8, 2.8),
    (0.0, 3.4),
    (1.8, 2.8),
]
HUMP = [0, 0.04, 0.08, 0.12, 0.5, 0.64, 0.78, 0.9, 1.0]  # back half level: the third loop

# passes through the parent as in sc.both / sc.blo / sc.flo, at the same depth in r:
# in at the left (back -> front), out at the right (front -> back)
PASSES: dict[str, tuple[list[Point], list[Point]]] = {
    "both": (
        [
            (-0.13, -0.42, -3.2),
            (-0.13, -1.90, -1.2),
            (-0.13, -2.11, 0.0),
            (-0.13, -1.90, 1.2),
            (-0.13, -0.42, 3.2),
        ],
        [
            (0.13, -0.42, 3.2),
            (0.13, -1.90, 1.2),
            (0.13, -2.11, 0.0),
            (0.13, -1.90, -1.2),
            (0.13, -0.42, -3.2),
        ],
    ),
    "blo": (
        [
            (-0.13, 0.85, -3.2),
            (-0.13, -0.21, -2.4),
            (-0.13, -1.06, 0.0),
            (-0.13, -1.69, 1.6),
            (-0.13, -0.42, 3.2),
        ],
        [
            (0.13, -0.42, 3.2),
            (0.13, -1.69, 1.6),
            (0.13, -1.06, 0.0),
            (0.13, -0.21, -2.4),
            (0.13, 0.85, -3.2),
        ],
    ),
    "flo": (
        [
            (-0.13, -0.42, -3.2),
            (-0.13, -1.69, -1.6),
            (-0.13, -1.06, 0.0),
            (-0.13, -0.21, 2.4),
            (-0.13, 0.85, 3.2),
        ],
        [
            (0.13, 0.85, 3.2),
            (0.13, -0.21, 2.4),
            (0.13, -1.06, 0.0),
            (0.13, -1.69, -1.6),
            (0.13, -0.42, -3.2),
        ],
    ),
}


def coil(ring, start: int, top: float, drops: list[float], centre=lambda v: 0.0) -> list[Point]:
    """Clockwise wraps from ring index `start` (0 right, 2 back, 4 left, 6 front), dropping
    `drops[k]` below `top` at the k-th 45 deg step; centre(v) is the axis' u in r."""
    out = []
    for k, d in enumerate(drops):
        u, n = ring[(start + k) % 8]
        v = top - d
        out.append(((u + centre(v)) / W, v, n))
    return out


def helix(pitch: float, turns: int, back: float = 0.5) -> list[float]:
    """Drops per 45 deg step: `back` of each pitch on the back half, the rest on the front
    half, so the bar across the front slants more than the back."""
    one = [back * pitch * k / 4 for k in range(5)]
    one += [pitch * (back + (1 - back) * k / 4) for k in range(1, 5)]
    return [0.0] + [t * pitch + d for t in range(turns) for d in one[1:]]


def _top_left(T: float) -> list[Point]:
    return [(-0.50, T, 0.0), (-0.40, T - 2.11, -1.4), (-0.22, T - 4.0, -1.25)]


def _front_loop(T: float) -> list[Point]:
    return [(-0.22, T - 3.8, 1.2), (-0.36, T - 1.52, 1.2), (0.02, T, 1.2), (0.36, T - 1.52, 1.2)]


def _top_right(T: float) -> list[Point]:
    return [(0.22, T - 4.0, -1.25), (0.40, T - 2.11, -1.4), (0.40, T - 0.17, -1.2), (0.50, T, 0.0)]


def _units(T: float, pts: list[Point], anchors: list[int]) -> list[tuple[float, float, float, int]]:
    return [(u, v / T, n, a) for (u, v, n), a in zip(pts, anchors, strict=True)]


def tall(height: float, wraps: list[Point], loop: str = "both", top_in: float = 6.0):
    """V-top and passes as sc; in between a post of four strands, `top_in` r under the top;
    the wraps are drawn on the strand coming down on the right after the front loop."""
    T = height * W
    into, out = PASSES[loop]
    p = _top_left(T)
    p += [(-B / W, T - top_in, -BN), (-B / W, 4.5, -BN), (-0.15, 2.11, -2.4)]
    p += into
    p += [(-0.15, 2.4, 2.4), (-B / W, 4.5, BN), (-B / W, T - top_in, BN)]
    p += _front_loop(T)
    p += wraps
    p += [(0.37, 2.96, 2.2)]  # the wrapped strand stays at the right edge, as in sc
    p += out
    p += [(0.15, 2.11, -2.4), (B / W, 4.5, -BN), (B / W, T - top_in, -BN)]
    p += _top_right(T)
    return _units(T, p, [0] * len(p))


Wraps = Callable[[Callable[[float], float]], list[Point]]


def tall_dec(
    height: float, joint: float, left: Wraps, right: Wraps, top_in: float = 6.0, joined=None
):
    """XYtog: from each parent an unfinished half post (one pass through the parent's
    middle, anchor 1 / 2), joined `joint` r above the base into the four-strand post under
    one V. left/right(centre) give each half post's wraps, centre(v) its axis in r;
    `joined` replaces the right half's strand above the joint by a wrap around the post."""
    T = height * W
    if not joint < T - top_in:
        raise ValueError("the half posts must join below the four-strand post")
    foot = 0.5 * W  # parents sit half a stitch to either side of the base

    def c_left(v: float) -> float:
        return -B - (foot - B) * max(0.0, 1.0 - v / joint)

    def c_right(v: float) -> float:
        return -c_left(v)

    into = [(0.0, v, n) for _, v, n in PASSES["both"][0]]
    out = [(0.0, v, n) for _, v, n in PASSES["both"][1]]
    p = _top_left(T) + [(-B / W, T - top_in, -BN), (-B / W, joint, -BN)]
    p += left(c_left) + [(c_left(2.11) / W, 2.11, -2.4)]
    a = [0] * len(p) + [1] * len(into)
    p += into
    p += [(c_left(2.4) / W, 2.4, 2.4), (c_left(4.5) / W, 4.5, BN), (-B / W, joint, BN)]
    p += [(-B / W, T - top_in, BN)] + _front_loop(T)
    if joined:
        p += joined
    else:
        p += [(B / W, T - top_in, BN), (B / W, joint, BN)] + right(c_right)
    p += [(c_right(2.4) / W, 2.4, 2.4)]
    a += [0] * (len(p) - len(a)) + [2] * len(out)
    p += out
    p += [(c_right(2.11) / W, 2.11, -2.4), (c_right(4.5) / W, 4.5, -BN), (B / W, joint, -BN)]
    p += [(B / W, T - top_in, -BN)] + _top_right(T)
    a += [0] * (len(p) - len(a))
    return _units(T, p, a)


def templates() -> dict[str, list[tuple[float, float, float, int]]]:
    hdc_wrap = coil(RING4, 0, 9.1, [4.6 * x for x in HUMP])
    dc_wrap = coil(RING4, 0, 11.5, helix(6.5, 1, back=0.35))
    tr_wrap = coil(RING4, 0, 18.0, helix(6.0, 2, back=0.35))
    out = {}
    for loop in ("both", "blo", "flo"):
        out[f"hdc.{loop}"] = tall(1.5, hdc_wrap, loop, top_in=4.6)
        out[f"dc.{loop}"] = tall(2.0, dc_wrap, loop)
        out[f"tr.{loop}"] = tall(3.0, tr_wrap, loop)
    out["hdc_dec.both"] = tall_dec(
        1.5, 5.0, lambda c: [], lambda c: [], top_in=4.6, joined=hdc_wrap
    )
    out["dc_dec.both"] = tall_dec(
        2.0,
        11.4,
        lambda c: coil(RING2, 2, 8.0, helix(4.4, 1), c),
        lambda c: coil(RING2, 6, 10.2, helix(4.4, 1), c),
        top_in=5.0,
    )
    out["tr_dec.both"] = tall_dec(
        3.0,
        18.4,
        lambda c: coil(RING2, 2, 14.0, helix(4.5, 2), c),
        lambda c: coil(RING2, 6, 16.3, helix(4.5, 2), c),
    )
    return out


MARK = "# Tall stitches (hdc, dc, tr)"
INTRO = f"""{MARK}: generated by stitchcraft_core/yarn/design.py, edit the shapes there.
# V-top and passes through the parent as in sc, at the same depth in yarn radii (so v values
# shrink with the height); in between a narrow post of four strands at u = +-0.13, n = +-1.2,
# narrower than the V, so dc fabric shows gaps between the posts. Each yarn-over is a wrap
# around the whole post, drawn on the strand that comes down on the right after the front
# loop: clockwise seen from the top, one point every 45 deg, 2.2 radii outside the post
# strands. The side of a wrap facing the next stitch is half a turn higher than the next
# stitch's wrap facing back, so neighbouring wraps pass each other without touching."""
COMMENTS = {
    "hdc.both": """\
Half double crochet: one yarn-over, then one pull through all three loops: a short
post with one wrap sitting high. Its back half runs level under the V as the third
loop (the "camel bump" on the back), the front half drops diagonally.""",
    "hdc.blo": "Back / front loop only: passes as in sc.blo / sc.flo.",
    "dc.both": """\
Double crochet: one yarn-over, closed by two "pull through 2": a long post with one
wrap mid-way, slanting across the front.""",
    "tr.both": 'Treble crochet: two yarn-overs, three "pull through 2": two wraps.',
    "hdc_dec.both": """\
hdc2tog: a loop pulled up through the middle of each parent, the legs join under one
V; one yarn-over around all of it, high as in hdc.""",
    "dc_dec.both": """\
dc2tog / tr2tog: from each parent an unfinished half post with its own wrap(s), the
halves join at about two thirds of the height into the four-strand post under one V.
The wraps of the two halves are staggered by half a turn where they face each other.""",
}


def section() -> str:
    """The generated end of templates.toml, from MARK on."""
    parts = [INTRO, ""]
    for name, pts in templates().items():
        parts += [f"# {line}" for line in COMMENTS.get(name, "").splitlines()]
        parts += [f"[{name}]", "points = ["]
        parts += [f"  [{u:6.2f}, {v:7.3f}, {n:5.1f}, {a}]," for u, v, n, a in pts]
        parts += ["]", ""]
    return "\n".join(parts)


def main() -> None:
    path = data_dir() / "stitches" / "templates.toml"
    head = path.read_text(encoding="utf-8").split(MARK)[0]
    path.write_text(head + section(), encoding="utf-8")


if __name__ == "__main__":
    main()

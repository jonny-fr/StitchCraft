"""M2 constructs: several stitches into one, skips, invisible decreases, XYtog."""

import pytest
from stitchcraft_core.graph import build_graph
from stitchcraft_core.ir import Into, Loop, Macro, Skip, Stitch
from stitchcraft_core.notation import parse
from stitchcraft_core.validate import validate


def only_row(text: str, dialect: str, index: int = -1):
    res = parse(text, dialect=dialect)
    assert [d for d in res.diagnostics if d.severity != "info"] == []
    return res.pattern.parts[0].rows[index]


def counts(text: str, dialect: str) -> list[int]:
    res = validate(text, dialect=dialect)
    assert res.ok, res.diagnostics
    return [r["actual"] for r in res.rows]


@pytest.mark.parametrize(
    ("text", "dialect"),
    [
        ("Rd. 2: (2 fM in 1 M) x6 (12)", "de"),
        ("Rd. 2: (2 fM in eine M) x6 (12)", "de"),
        ("Rnd 2: (2 sc in next st) x6 (12)", "en-US"),
        ("Rnd 2: (2 dc in same st) x6 (12)", "en-UK"),
    ],
)
def test_n_stitches_into_one_is_an_increase(text, dialect):
    row = only_row(text, dialect)
    (inner,) = row.instructions[0].body
    assert isinstance(inner, Into)
    (st,) = inner.body
    assert isinstance(st, Stitch) and (st.type, st.count) == ("sc", 2)


def test_increase_written_out_links_like_inc():
    assert counts("6 fM in MR (6)\n(2 fM in 1 M) x6 (12)", "de") == [6, 12]
    g = build_graph(parse("6 fM in MR\n(2 fM in 1 M) x6", dialect="de").pattern)
    second = g.rows[1].node_ids
    assert g.nodes[second[0]].parents == g.nodes[second[1]].parents


def test_shell_of_double_crochets():
    text = "R 1: 14 Lm, wenden\nR 2: 1 fM, (2 M überspr., 5 Stb in 1 M, 2 M überspr., 1 fM) x2 (13)"
    assert counts(text, "de") == [14, 13]


def test_v_stitch_group_into_one_stitch():
    text = "Row 1: ch 7, turn\nRow 2: (dc, ch 1, dc) in next st, sk 1, (dc, ch 1, dc) in next st"
    res = validate(text, dialect="en-US")
    assert res.ok, res.diagnostics
    (w,) = [d for d in res.diagnostics if d.code == "W_UNWORKED"]
    assert w.params["left"] == 4  # 7 chains, 3 worked or skipped


@pytest.mark.parametrize(
    ("text", "dialect", "n"),
    [
        ("R 2: 1 M überspringen, 3 fM", "de", 1),
        ("R 2: 2 M überspr., 3 fM", "de", 2),
        ("Row 2: sk 2, 3 sc", "en-US", 2),
        ("Row 2: skip 1 st, 3 sc", "en-US", 1),
        ("Row 2: sk next st, 3 sc", "en-US", 1),
    ],
)
def test_skip(text, dialect, n):
    row = only_row(text, dialect)
    skip = row.instructions[0]
    assert isinstance(skip, Skip) and skip.count == n


def test_skip_consumes_parents_without_making_stitches():
    assert counts("R 1: 6 Lm, wenden\nR 2: 2 M überspr., 3 fM (3)", "de") == [6, 3]


@pytest.mark.parametrize(
    ("text", "dialect"),
    [
        ("Rd. 3: 6x uabn (6)", "de"),
        ("Rd. 3: 6x unsichtbare Abnahme (6)", "de"),
        ("Rnd 3: invdec x6", "en-US"),
    ],
)
def test_invisible_decrease_works_front_loops(text, dialect):
    row = only_row(text, dialect)
    (m,) = row.instructions[0].body
    assert isinstance(m, Macro) and m.kind == "dec" and m.loop is Loop.FLO


@pytest.mark.parametrize(
    ("text", "dialect", "stitch", "merge"),
    [
        ("Row 2: sc2tog", "en-US", "sc", 2),
        ("Row 2: hdc2tog", "en-US", "hdc", 2),
        ("Row 2: dc3tog", "en-US", "dc", 3),
        ("Row 2: dc2tog", "en-UK", "sc", 2),
        ("Row 2: tr2tog", "en-UK", "dc", 2),
        ("R 2: 2 fM zus. abm.", "de", "sc", 2),
        ("R 2: 3 Stb zusammen abmaschen", "de", "dc", 3),
    ],
)
def test_stitches_together(text, dialect, stitch, merge):
    (m,) = only_row(text, dialect).instructions
    assert isinstance(m, Macro) and (m.kind, m.stitch, m.merge) == ("dec", stitch, merge)


def test_three_together_takes_three_parents():
    g = build_graph(parse("R 1: 7 Lm, wenden\nR 2: 2x 3 fM zus. abm.", dialect="de").pattern)
    last = g.rows[1].node_ids
    assert [len(g.nodes[i].parents) for i in last] == [3, 3]


def test_dc_into_magic_ring():
    assert counts("12 Stb in MR (12)", "de") == [12]

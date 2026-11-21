"""IR -> text in a dialect, and back: parse(format(ir)) == ir."""

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from stitchcraft_core.ir import (
    ColorChange,
    Each,
    Into,
    Loop,
    Macro,
    Part,
    Pattern,
    Repeat,
    Row,
    Skip,
    Stitch,
    Turn,
)
from stitchcraft_core.notation import parse
from stitchcraft_core.notation.printer import format_pattern
from stitchcraft_core.pipeline import normalised_ir

DIALECTS = ["de", "en-US", "en-UK"]


def roundtrip(pattern: Pattern, dialect: str) -> Pattern:
    text = format_pattern(pattern, dialect)
    res = parse(text, dialect=dialect)
    assert [d for d in res.diagnostics if d.severity != "info"] == [], text
    return res.pattern


def test_formats_rounds_in_german():
    text = "Rd. 1: 6 fM in MR (6)\nRd. 2: 6x zun (12)\nRd. 3 (nur hMg): (1 fM, zun) x6 (18)"
    assert format_pattern(parse(text, "de").pattern, "de") == text


def test_formats_us_rows_with_turn_and_shell():
    text = "Row 1: 14 ch, turn\nRow 2: 1 sc, (sk 2, 5 dc in next st, sk 2, 1 sc) x2 (13)"
    assert format_pattern(parse(text, "en-US").pattern, "en-US") == text


def test_same_ir_prints_in_uk_terms():
    pattern = parse("Rd. 1: 6 fM in MR (6)\nRd. 2: 6x 2 Stb zus. abm.", "de").pattern
    assert format_pattern(pattern, "en-UK") == "Rnd 1: 6 dc in MR (6)\nRnd 2: 6x tr2tog"


# --- property: any IR the parser can produce survives printing and parsing -----------------

TYPES = ["sc", "hdc", "dc", "tr", "slst"]
loops = st.sampled_from([Loop.BOTH, Loop.BOTH, Loop.BLO, Loop.FLO])
counts = st.integers(1, 12)


def stitch(loop_ok: bool = True):
    return st.builds(
        Stitch,
        type=st.sampled_from([*TYPES, "ch"]),
        count=counts,
        loop=loops if loop_ok else st.just(Loop.BOTH),
    )


macro = st.one_of(
    st.builds(Macro, kind=st.just("inc"), count=counts, loop=loops),
    st.builds(Macro, kind=st.just("dec"), count=counts, loop=loops),
    st.builds(
        Macro,
        kind=st.just("dec"),
        stitch=st.sampled_from(TYPES[:4]),
        merge=st.integers(2, 4),
        loop=st.just(Loop.BOTH),
    ),
)
into = st.builds(
    Into,
    body=st.one_of(
        st.lists(
            st.builds(Stitch, type=st.sampled_from(TYPES[:4]), count=st.integers(2, 7)),
            min_size=1,
            max_size=1,
        ),
        st.tuples(st.sampled_from(TYPES[:4]), st.integers(1, 3)).map(
            lambda t: [Stitch(t[0]), Stitch("ch", t[1]), Stitch(t[0])]
        ),
    ),
)
skip = st.builds(Skip, count=st.integers(1, 3))
color = st.builds(ColorChange, color=st.sampled_from(["A", "B", "C", "MC", "CC1"]))
simple = st.one_of(stitch(), macro, into, skip, color)
repeat = st.builds(
    Repeat,
    body=st.lists(st.one_of(stitch(), macro, into, skip), min_size=1, max_size=3),
    times=st.integers(2, 8),
)
body = st.lists(st.one_of(simple, repeat), min_size=1, max_size=5)


@st.composite
def patterns(draw):
    rows = []
    kind = draw(st.sampled_from(["round", "row"]))
    for number in range(1, draw(st.integers(1, 4)) + 1):
        instrs = draw(body)
        if number == 1 and kind == "round":
            instrs = [Stitch(draw(st.sampled_from(TYPES[:4])), draw(counts), into_ring=True)]
        if kind == "row" and draw(st.booleans()):
            instrs = [*instrs, Turn()]
        expected = draw(st.one_of(st.none(), st.integers(1, 99)))
        rows.append(Row(number, kind, instrs, expected))
    # a palette must define every code used, or the parser warns
    palette = draw(st.sampled_from([{}, dict.fromkeys(["A", "B", "C", "MC", "CC1"], "#c0392b")]))
    return Pattern(dialect="de", parts=[Part(rows)], palette=palette)


@pytest.mark.parametrize("dialect", DIALECTS)
@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(pattern=patterns())
def test_roundtrip_property(dialect, pattern):
    pattern.dialect = dialect
    assert normalised_ir(roundtrip(pattern, dialect)) == normalised_ir(pattern)


def test_each_roundtrips():
    p = Pattern("de", [Part([Row(1, "round", [Each("sc", 2)], 12)])])
    assert normalised_ir(roundtrip(p, "de")) == normalised_ir(p)

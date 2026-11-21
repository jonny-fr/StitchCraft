import pytest
from stitchcraft_core.ir import Macro, Repeat, Stitch
from stitchcraft_core.notation import parse
from stitchcraft_core.notation.detect import detect_dialect


@pytest.mark.parametrize(
    ("text", "dialect"),
    [
        ("Rd. 1: 6 fM in MR (6)\nRd. 2: 6x zun (12)", "de"),
        ("Rnd 1: 6 sc in MR (6)\nRnd 2: inc x6 (12)", "en-US"),
        ("Rnd 1: 6 dc in MR (6)\nRnd 2: (1 dc, 1 ss) x2", "en-UK"),
        ("Row 1: ch 11, turn\nRow 2: 10 htr, turn", "en-UK"),
        ("Row 1: ch 11, turn\nRow 2: 10 hdc, turn", "en-US"),
        ("Rnd 1: 6 dc in MR\nRnd 2: 12 dc (UK terms)", "en-UK"),
    ],
)
def test_detects_dialect_from_vocabulary(text, dialect):
    d = detect_dialect(text)
    assert d.dialect == dialect
    assert not d.ambiguous


def test_ch_dc_tr_only_is_ambiguous_between_us_and_uk():
    d = detect_dialect("Rnd 1: 12 dc in MR (12)\nRnd 2: 24 tr (24)")
    assert d.ambiguous
    assert d.candidates == ["en-US", "en-UK"]


def test_auto_parse_warns_on_ambiguous_dialect_instead_of_silently_assuming():
    res = parse("Rnd 1: 12 dc in MR (12)", dialect="auto")
    (warn,) = [d for d in res.diagnostics if d.code == "W_AMBIGUOUS_DIALECT"]
    assert warn.params == {"chosen": "en-US", "candidates": ["en-US", "en-UK"]}
    assert res.pattern.dialect == "en-US"


def test_auto_parse_uses_detected_dialect():
    res = parse("Rnd 1: 6 htr in MR (6)", dialect="auto")
    assert res.pattern.dialect == "en-UK"
    (st,) = res.pattern.parts[0].rows[0].instructions
    assert st.type == "hdc"
    assert not res.diagnostics


def test_glossary_single_terms_become_local_vocabulary():
    text = "Abkürzungen: fe = feste Masche, Zu = Zunahme\n\nRd. 1: 6 fe in MR (6)\nRd. 2: 6 Zu (12)"
    res = parse(text, dialect="de")
    assert not res.diagnostics
    r1, r2 = res.pattern.parts[0].rows
    (st,) = r1.instructions
    assert isinstance(st, Stitch) and (st.type, st.count, st.into_ring) == ("sc", 6, True)
    (m,) = r2.instructions
    assert isinstance(m, Macro) and (m.kind, m.count) == ("inc", 6)


def test_glossary_block_over_several_lines_and_english_header():
    text = (
        "Abbreviations:\nsgl = single crochet\nup - increase\n\n"
        "Rnd 1: 6 sgl in MR\nRnd 2: up x6 (12)"
    )
    res = parse(text, dialect="en-US")
    assert not res.diagnostics
    assert [r.number for r in res.pattern.parts[0].rows] == [1, 2]


def test_glossary_sequence_definition_expands_where_used():
    text = "Abkürzungen: Muster = 1 fM, zun\nRd. 1: 6 fM in MR (6)\nRd. 2: 6 Muster (18)"
    res = parse(text, dialect="de")
    assert not res.diagnostics
    (rep,) = res.pattern.parts[0].rows[1].instructions
    assert isinstance(rep, Repeat) and rep.times == 6
    assert [type(i).__name__ for i in rep.body] == ["Stitch", "Macro"]


def test_glossary_entry_with_unknown_meaning_is_warned():
    res = parse("Abkürzungen: xy = irgendwas Seltsames\nRd. 1: 6 fM in MR", dialect="de")
    (w,) = res.diagnostics
    assert w.code == "W_GLOSSARY_UNKNOWN"
    assert w.params == {"abbr": "xy", "meaning": "irgendwas Seltsames"}

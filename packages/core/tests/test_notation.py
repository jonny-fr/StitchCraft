import pytest
from stitchcraft_core.ir import Each, Loop, Macro, Repeat, Stitch, Turn
from stitchcraft_core.notation import parse


def rows(text: str, dialect: str = "de"):
    result = parse(text, dialect=dialect)
    assert [d for d in result.diagnostics if d.severity == "error"] == []
    return result.pattern.parts[0].rows


def test_magic_ring_round_without_label_is_round_one():
    (row,) = rows("6 fM in MR")
    assert row.number == 1
    assert row.kind == "round"
    (st,) = row.instructions
    assert isinstance(st, Stitch)
    assert (st.type, st.count, st.into_ring) == ("sc", 6, True)


def test_prefix_repeat_and_count_check():
    (row,) = rows("Rd. 2: 6x zun (12)")
    assert row.number == 2
    assert row.expected_count == 12
    (rep,) = row.instructions
    assert isinstance(rep, Repeat) and rep.times == 6
    (inner,) = rep.body
    assert isinstance(inner, Macro) and inner.kind == "inc"


def test_parenthesised_repeat_with_postfix_times():
    (row,) = rows("Rd. 3: (1 fM, zun) x6 (18)")
    (rep,) = row.instructions
    assert isinstance(rep, Repeat) and rep.times == 6
    assert isinstance(rep.body[0], Stitch) and rep.body[0].count == 1
    assert isinstance(rep.body[1], Macro)
    assert row.expected_count == 18


def test_label_range_expands_to_one_row_per_number():
    parsed = rows("Rd. 7-12: 36 fM (36)")
    assert [r.number for r in parsed] == [7, 8, 9, 10, 11, 12]
    assert all(r.expected_count == 36 for r in parsed)


def test_back_loop_only_applies_to_following_stitches():
    (row,) = rows("Rd. 6: nur hMg 30 fM (30)")
    (st,) = row.instructions
    assert st.loop is Loop.BLO


def test_back_loop_in_label_parentheses_applies_to_row():
    (row,) = rows("Rd. 6 (nur hMg): 30 fM (30)")
    assert row.instructions[0].loop is Loop.BLO


def test_flat_rows_with_turn():
    parsed = rows("R 1: 16 Lm, wenden\nR 2: 15 fM, 1 Lm, wenden (15)")
    assert [r.kind for r in parsed] == ["row", "row"]
    assert isinstance(parsed[0].instructions[-1], Turn)
    assert [type(i) for i in parsed[1].instructions] == [Stitch, Stitch, Turn]


@pytest.mark.parametrize("variant", ["fM", "FM", "fm", "f M", "feste Maschen"])
def test_german_spelling_variants_normalise(variant):
    (row,) = rows(f"6 {variant} in MR")
    assert row.instructions[0].type == "sc"


def test_each_stitch_around_in_german():
    (row,) = rows("Rd. 7: fM rundum (36)")
    (each,) = row.instructions
    assert isinstance(each, Each) and each.type == "sc"


def test_unlabelled_lines_continue_numbering():
    parsed = rows("6 fM in MR\n6x zun (12)\n(1 fM, zun) x6 (18)")
    assert [r.number for r in parsed] == [1, 2, 3]


def test_en_us_vocabulary():
    parsed = rows(
        "Rnd 1: 6 sc in magic ring (6)\n"
        "Rnd 2: inc x6 (12)\n"
        "Rnd 3: [sc, inc] x6 (18)\n"
        "Rnd 4: BLO sc around (18)\n"
        "Rnd 5: (sc, dec) x6 (12)",
        dialect="en-US",
    )
    assert parsed[0].instructions[0].type == "sc"
    inc_rep = parsed[1].instructions[0]
    assert isinstance(inc_rep, Repeat) and inc_rep.times == 6
    assert isinstance(inc_rep.body[0], Macro)
    assert isinstance(parsed[2].instructions[0], Repeat)
    assert parsed[3].instructions[0].loop is Loop.BLO
    assert parsed[4].instructions[0].body[1].kind == "dec"


def test_en_us_stitch_count_after_stitch_name():
    (row,) = rows("Row 2: sc 15, ch 1, turn (15)", dialect="en-US")
    assert row.kind == "row"
    assert row.instructions[0].count == 15


def test_en_uk_double_crochet_means_single_crochet():
    (row,) = rows("Rnd 1: 6 dc in magic ring (6)", dialect="en-UK")
    assert row.instructions[0].type == "sc"


def test_en_us_double_crochet_is_a_tall_stitch():
    (row,) = rows("Rnd 1: 6 dc in magic ring (6)", dialect="en-US")
    assert row.instructions[0].type == "dc"


def test_prose_line_is_warning_not_failure():
    result = parse("6 fM in MR\nDie Kugel gut ausstopfen und schön machen\n6x zun (12)")
    codes = [d.code for d in result.diagnostics]
    assert codes == ["W_PROSE"]
    assert result.diagnostics[0].span.line == 2
    assert len(result.pattern.parts[0].rows) == 2


def test_labelled_garbage_is_syntax_error_with_location():
    result = parse("Rd. 1: 6 fM in MR\nRd. 2: 6x ( zun")
    (diag,) = result.diagnostics
    assert diag.code == "E_SYNTAX"
    assert diag.severity == "error"
    assert diag.span.line == 2


def test_finishing_instructions_are_noted_not_warned():
    result = parse("6 fM in MR\nFaden abschneiden")
    assert [d.code for d in result.diagnostics] == ["I_IGNORED"]


def test_spans_point_at_source_text():
    text = "Rd. 1: 6 fM in MR\nRd. 2: 6x zun (12)"
    result = parse(text)
    rep = result.pattern.parts[0].rows[1].instructions[0]
    inner = rep.body[0]
    assert text[inner.span.start : inner.span.end] == "zun"
    assert inner.span.line == 2


def test_unknown_dialect_raises():
    with pytest.raises(ValueError):
        parse("6 fM in MR", dialect="fr")

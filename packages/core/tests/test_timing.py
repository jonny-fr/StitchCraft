import typing

import pytest
from conftest import reference_pattern
from stitchcraft_core.data import load_toml
from stitchcraft_core.params import Params, library
from stitchcraft_core.timing import PACES, Pace
from stitchcraft_core.validate import validate

T = load_toml("timing.toml")
ST, MAC, EX = T["stitch"], T["macro"], T["extra"]


def total(text: str, **kw) -> float:
    est = validate(text, **kw).time_estimate
    assert est is not None
    return sum(r.seconds for r in est.per_row)


# H1: the known pieces add up to exactly the table values (geuebt, 2 mm cotton: factor 1)


def test_sphere_is_exactly_the_table_sum():
    est = validate(reference_pattern("3-sphere")).time_estimate
    assert est is not None
    # 432 sc, 60 of them from increases, 30 decreases; magic ring; 17 rounds
    expected = 432 * ST["sc"] + 60 * MAC["inc"] + 30 * MAC["dec"] + EX["ring"] + 17 * EX["row"]
    assert sum(r.seconds for r in est.per_row) == expected
    assert est.seconds_low == round(expected * (1 - T["spread"]))
    assert est.seconds_high == round(expected * (1 + T["spread"]))
    assert [r.number for r in est.per_row] == list(range(1, 18))
    assert est.per_row[0].seconds == EX["ring"] + 6 * ST["sc"] + EX["row"]


def test_cup_is_exactly_the_table_sum():
    expected = 420 * ST["sc"] + 48 * MAC["inc"] + EX["ring"] + 16 * EX["row"]
    assert total(reference_pattern("4-cup")) == expected


def test_dc_square_is_exactly_the_table_sum():
    # 16 foundation chains, 8 rows of 3 turning chains and 15 dc
    expected = 40 * ST["ch"] + 120 * ST["dc"] + 9 * EX["row"]
    est = validate(reference_pattern("6-dc-square")).time_estimate
    assert est is not None
    assert sum(r.seconds for r in est.per_row) == expected
    assert [r.kind for r in est.per_row] == ["row"] * 9


def test_time_grows_with_the_stitch_count():
    times = [total(f"Rd. 1: 6 fM in MR (6)\nRd. 2: {n} fM") for n in (6, 12, 18, 36, 72)]
    assert times == sorted(times) and len(set(times)) == len(times)


def test_dc_takes_longer_than_sc():
    assert total("Rd. 1: 12 Stb in MR (12)") > total("Rd. 1: 12 fM in MR (12)")
    assert ST["sc"] < ST["hdc"] < ST["dc"] < ST["tr"]


def test_invisible_decrease_and_colour_change_use_their_table_values():
    base = "Rd. 1: 6 fM in MR (6)\nRd. 2: 6x zun (12)\n"
    assert total(base + "Rd. 3: 6x uabn (6)") == total(base + "Rd. 3: 6x abn (6)") - 6 * (
        MAC["dec"] - MAC["invdec"]
    )
    plain = total(base + "Rd. 3: 12 fM (12)")
    assert total(base + "Rd. 3: 6 fM, FbW B, 6 fM (12)") == plain + EX["color_change"]
    assert total(base + "FbW B\nRd. 3: 12 fM (12)") == plain + EX["color_change"]


def test_decrease_of_three_counts_two_extra_stitches():
    base = "R 1: 10 Lm, wenden\nR 2: 3 Lm, 9 Stb, wenden (9)\nR 3: 3 Lm, "
    three = total(base + "3x 3 Stb zus. abm. (3)")
    assert three == total(base + "3 Stb (3)") + 3 * 2 * MAC["dec"]


def test_every_library_stitch_has_a_time():
    assert set(library()["stitch"]) - {"ring"} <= set(ST)


# pace, custom pace, yarn


def test_pace_ids_and_materials_match_the_table():
    assert set(typing.get_args(Pace)) == set(PACES) == set(T["pace"])
    materials = typing.get_args(typing.get_type_hints(Params)["material"])
    assert set(materials) == set(T["material"])


def test_pace_orders_the_estimate():
    text = reference_pattern("3-sphere")
    slow, normal, fast = (total(text, pace=p) for p in ("anfaenger", "geuebt", "schnell"))
    assert slow == normal * T["pace"]["anfaenger"]
    assert slow > normal > fast


def test_custom_stitches_per_minute_replaces_the_table_scale():
    text = reference_pattern("3-sphere")
    sc_per_minute = 60 / ST["sc"]
    assert total(text, stitches_per_minute=sc_per_minute) == total(text)
    assert total(text, stitches_per_minute=sc_per_minute / 2) == 2 * total(text)
    # the measured pace already holds the person and the yarn: pace and yarn change nothing
    thick = Params(yarn_mm=6.0, material="mohair")
    custom = total(text, stitches_per_minute=12, pace="schnell", params=thick)
    assert custom == total(text, stitches_per_minute=12)


def test_thick_yarn_is_faster_per_stitch_and_mohair_slower():
    text = reference_pattern("4-cup")
    thick, thin = Params(yarn_mm=6.0), Params(yarn_mm=1.0)
    assert total(text, params=thick) < total(text) < total(text, params=thin)
    assert total(text, params=Params(material="mohair")) == pytest.approx(
        total(text) * T["material"]["mohair"]
    )
    # the yarn factor is small and bounded
    assert total(text, params=Params(yarn_mm=14.0)) == pytest.approx(total(text) * T["yarn"]["min"])


@pytest.mark.parametrize(
    ("kw", "message"),
    [({"pace": "turbo"}, "pace"), ({"stitches_per_minute": 0}, "stitches_per_minute")],
)
def test_bad_pace_is_rejected(kw, message):
    with pytest.raises(ValueError, match=message):
        validate("Rd. 1: 6 fM in MR (6)", **kw)


def test_nothing_to_crochet_gives_no_estimate():
    assert validate("").time_estimate is None
    assert validate("Rd. 1: 6 fM in MR (6)\nRd. 2: 6000 fM").time_estimate is None

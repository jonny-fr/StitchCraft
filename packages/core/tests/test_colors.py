import io

import numpy as np
import pytest
from stitchcraft_core.export import glb_bytes, point_colors, shape_json
from stitchcraft_core.graph import build_graph
from stitchcraft_core.notation import parse
from stitchcraft_core.params import Params
from stitchcraft_core.pipeline import preview

DISC = "Rd. 1: 6 fM in MR (6)\nRd. 2: 6x zun (12)\nRd. 3: (1 fM, zun) x6 (18)"


def colours(text: str, dialect: str = "de"):
    result = parse(text, dialect=dialect)
    g = build_graph(result.pattern)
    assert [d for d in result.diagnostics + g.diagnostics if d.severity != "info"] == []
    return [[g.nodes[n].color for n in row.node_ids] for row in g.rows]


def test_without_colour_changes_everything_is_the_first_colour():
    assert {c for row in colours(DISC) for c in row} == {"A"}


def test_inline_change_applies_from_the_next_stitch():
    rows = colours("Rd. 1: 6 fM in MR (6)\nRd. 2: 3 fM, FbW B, 3 fM (6)")
    assert rows[1] == ["A"] * 3 + ["B"] * 3


def test_label_colour_applies_to_the_row_and_carries_on():
    rows = colours("Rd. 1: 6 fM in MR (6)\nRd. 2 (B): 6x zun (12)\nRd. 3: 12 fM (12)")
    assert rows[0] == ["A"] * 6 and rows[1] == ["B"] * 12 and rows[2] == ["B"] * 12


def test_label_range_with_loop_and_colour():
    rows = colours("Rd. 1: 6 fM in MR (6)\nRd. 2-3 (nur hMg) (B): 6 fM (6)")
    assert rows[1] == rows[2] == ["B"] * 6


def test_change_on_its_own_line_starts_with_the_next_row_without_numbering_it():
    result = parse("Rd. 1: 6 fM in MR (6)\nFarbwechsel zu B\n6 fM (6)")
    assert [r.number for r in result.pattern.parts[0].rows] == [1, 2]
    rows = colours("Rd. 1: 6 fM in MR (6)\nFarbwechsel zu B\n6 fM (6)")
    assert rows[1] == ["B"] * 6


@pytest.mark.parametrize(
    "change", ["FbW B", "Farbwechsel auf B", "mit Farbe B", "in Farbe B", "fbw B"]
)
def test_german_change_spellings(change):
    assert colours(f"Rd. 1: 6 fM in MR (6)\nRd. 2: {change}, 6 fM (6)")[1] == ["B"] * 6


def test_palette_line_defines_colours_and_the_start_colour():
    result = parse("Farben: B = rot, A = creme, C = #2B2B2B\nRd. 1: 6 fM in MR (6)")
    palette = result.pattern.palette
    assert list(palette) == ["B", "A", "C"]
    assert palette["C"] == "#2b2b2b" and palette["B"].startswith("#")
    assert colours("Farben: B = rot, A = creme\nRd. 1: 6 fM in MR (6)")[0] == ["B"] * 6


def test_colour_names_can_be_used_directly():
    assert colours("Rd. 1: 6 fM in MR (6)\nRd. 2: FbW Rot, 6 fM (6)")[1] == ["rot"] * 6


def test_unknown_names_are_warned():
    result = parse(
        "Farben: A = creme, B = schlumpfblau\nRd. 1: 6 fM in MR (6)\nRd. 2: FbW D, 6 fM (6)"
    )
    warned = [(d.code, d.params["name"], d.span.line) for d in result.diagnostics]
    assert warned == [("W_UNKNOWN_COLOR", "schlumpfblau", 1), ("W_UNKNOWN_COLOR", "D", 3)]


def test_without_palette_any_letter_code_is_fine():
    assert colours("Rd. 1: 6 fM in MR (6)\nRd. 2 (CC1): 6 fM (6)")[1] == ["CC1"] * 6


def test_turning_chain_is_still_found_after_a_colour_change():
    rows = colours("R 1: 15 Lm, wenden\nR 2: FbW B, 1 Lm, 14 fM, wenden (14)")
    assert rows[1] == ["B"] * 15


@pytest.mark.parametrize("dialect", ["en-US", "en-UK"])
def test_english_colour_changes(dialect):
    st = "sc" if dialect == "en-US" else "dc"
    text = (
        f"Colors: MC = white, CC1 = red\nRnd 1: 6 {st} in MR (6)\n"
        f"Rnd 2 (CC1): 2 {st} in each st (12)\nRnd 3: change to MC, 12 {st} (12)"
    )
    rows = colours(text, dialect)
    assert rows[0] == ["MC"] * 6 and rows[1] == ["CC1"] * 12 and rows[2] == ["MC"] * 12


@pytest.fixture(scope="module")
def striped():
    return preview(
        DISC.replace("Rd. 2:", "Rd. 2 (B):").replace("Rd. 3:", "Rd. 3 (A):"), "de", Params()
    )


def test_shape_json_lists_used_colours_with_hex(striped):
    data = shape_json(striped)
    assert [c["ref"] for c in data["palette"]] == ["A", "B"]
    assert all(c["hex"].startswith("#") and c["defined"] is False for c in data["palette"])
    assert {s["color"] for s in data["stitches"]} == {"A", "B"}


def test_point_colours_follow_the_stitches(striped):
    rgba = point_colors(striped)
    assert rgba.shape == (len(striped.yarn.points), 4) and rgba.dtype == np.uint8
    assert len({tuple(c) for c in rgba}) == 2


def test_glb_has_vertex_colours(striped):
    import trimesh

    blob = glb_bytes(striped.yarn, sides=6, rgba=point_colors(striped))
    (mesh,) = trimesh.load(io.BytesIO(blob), file_type="glb").geometry.values()
    assert len({tuple(c) for c in mesh.visual.vertex_colors}) == 2

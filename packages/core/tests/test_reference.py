"""Criteria against the reference pieces: A1/A2 against photographs (skipped until photos
and masks exist) and the M5 gate for piece 6, the dc square in de, en-US and en-UK."""

import time

import numpy as np
import pytest
from conftest import PIECES, REFERENCE_DIR
from stitchcraft_core.evaluation import evaluate_reference
from stitchcraft_core.gate import (
    FLAT_RMS_MAX,
    ROW_PITCH_RATIO,
    dialect_neutral_ir,
    flat_rms,
    graph_signature,
    m5_patterns,
    row_pitch,
)
from stitchcraft_core.params import Params
from stitchcraft_core.pipeline import preview
from stitchcraft_core.yarn import penetration_stats

pytestmark = pytest.mark.reference

P = Params()


@pytest.mark.parametrize("piece", PIECES[:4])
def test_a1_dimensions_within_ten_percent(piece):
    result = evaluate_reference(REFERENCE_DIR / piece)
    if not result.available:
        pytest.skip(f"{piece}: no measurements.toml yet")
    assert result.a1_ok, result.dimensions


@pytest.mark.parametrize("piece", PIECES[1:4])
def test_a2_silhouette_iou(piece):
    result = evaluate_reference(REFERENCE_DIR / piece)
    if not result.available or not result.ious:
        pytest.skip(f"{piece}: no silhouette masks yet")
    assert result.a2_ok, result.ious


@pytest.fixture(scope="module")
def dc_square():
    texts = m5_patterns(REFERENCE_DIR)
    return texts, {d: preview(t, d, P) for d, t in texts.items()}


def test_dc_square_is_written_in_three_dialects(dc_square):
    texts, _ = dc_square
    assert set(texts) == {"de", "en-US", "en-UK"}


def test_dc_square_same_in_every_dialect(dc_square):
    """The three versions give the same IR, the same graph and the same yarn path."""
    texts, previews = dc_square
    assert len({dialect_neutral_ir(t, d) for d, t in texts.items()}) == 1
    assert len({graph_signature(p) for p in previews.values()}) == 1
    assert len({p.yarn_hash for p in previews.values()}) == 1


def test_dc_square_a3_counts_and_parents(dc_square):
    _, previews = dc_square
    p = previews["de"]
    g = p.validation.graph
    assert p.ok, p.validation.diagnostics
    worked = [r for r in g.rows if not r.foundation]
    assert len(worked) == 8
    for row in worked:
        ids = g.counting_ids(row)
        assert len(ids) == row.expected == 15
        assert {g.nodes[n].type for n in ids} == {"dc"}
        assert all(len(g.nodes[n].parents) == 1 for n in ids)
    parents = [g.nodes[n].parents[0] for r in worked[1:] for n in g.counting_ids(r)]
    assert len(set(parents)) == len(parents)  # every dc of the row below gets one


def test_dc_square_a4_a5(dc_square):
    y = dc_square[1]["de"].yarn
    steps = np.linalg.norm(np.diff(y.points, axis=0), axis=1)
    b = np.flatnonzero(np.diff(y.stitch_ids) != 0)
    b = b[(b > 0) & (b < len(steps) - 1)]
    assert (steps[b] - np.maximum(steps[b - 1], steps[b + 1])).max() <= 0.05 * y.yarn_radius
    stats = penetration_stats(y)
    assert stats.max_depth <= 0.10 * y.yarn_radius, stats
    assert stats.affected_fraction <= 0.01, stats


def test_dc_square_a7_row_pitch_and_flat(dc_square):
    """dc rows are twice as tall as sc rows (library), the square stays flat."""
    sc = preview((REFERENCE_DIR / "1-square" / "pattern.txt").read_text(encoding="utf-8"), "de", P)
    ratio = row_pitch(dc_square[1]["de"]) / row_pitch(sc)
    assert ROW_PITCH_RATIO[0] <= ratio <= ROW_PITCH_RATIO[1]
    assert flat_rms(dc_square[1]["de"]) <= FLAT_RMS_MAX


def test_dc_square_a8_deterministic(dc_square):
    texts, previews = dc_square
    assert preview(texts["de"], "de", P).yarn_hash == previews["de"].yarn_hash


def test_dc_square_a9_preview_under_five_seconds(dc_square):
    texts, _ = dc_square
    t0 = time.perf_counter()
    preview(texts["de"], "de", P)
    assert time.perf_counter() - t0 < 5.0

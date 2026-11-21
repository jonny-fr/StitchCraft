"""A1/A2 against photographed reference pieces; skipped until photos and masks exist."""

import pytest
from conftest import PIECES, REFERENCE_DIR
from stitchcraft_core.evaluation import evaluate_reference

pytestmark = pytest.mark.reference


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

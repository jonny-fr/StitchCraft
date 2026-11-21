import numpy as np
import pytest
from conftest import reference_pattern
from stitchcraft_core.evaluation import (
    iou,
    main_dimensions,
    silhouette,
)
from stitchcraft_core.params import Params
from stitchcraft_core.pipeline import preview


@pytest.fixture(scope="module")
def cup():
    return preview(reference_pattern("4-cup"), "de", Params())


def test_cup_dimensions_are_diameter_and_height(cup):
    dims = main_dimensions(cup, form="open")
    # 30 stitches of 5.08 mm around -> ~48.5 mm across the stitch centres, plus the fabric
    # thickness on both sides (outermost strands at 3.2 radii, plus the radius itself)
    r = Params().yarn_radius_mm
    assert dims["width"] == pytest.approx(30 * 5.075 / np.pi + 2 * 4.2 * r, rel=0.05)
    assert dims["height"] > 40


def test_flat_dimensions_for_square():
    p = preview(reference_pattern("1-square"), "de", Params())
    dims = main_dimensions(p, form="flat")
    assert dims["width"] == pytest.approx(76, rel=0.1)
    assert dims["height"] == pytest.approx(76, rel=0.1)


def test_silhouette_iou_with_itself_is_one(cup):
    mask = silhouette(cup, view="front", mm_per_px=0.5)
    assert mask.dtype == bool and mask.any()
    assert iou(mask, mask) == pytest.approx(1.0)


def test_iou_aligns_by_centroid(cup):
    mask = silhouette(cup, view="front", mm_per_px=0.5)
    shifted = np.zeros((mask.shape[0] + 40, mask.shape[1] + 40), dtype=bool)
    shifted[25 : 25 + mask.shape[0], 10 : 10 + mask.shape[1]] = mask
    assert iou(mask, shifted) == pytest.approx(1.0, abs=0.02)


def test_iou_of_different_shapes_is_low(cup):
    mask = silhouette(cup, view="front", mm_per_px=0.5)
    top = silhouette(cup, view="top", mm_per_px=0.5)
    assert iou(mask, top) < 0.85

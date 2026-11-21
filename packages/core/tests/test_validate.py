import time

from conftest import reference_pattern
from stitchcraft_core.validate import validate


def test_validate_reports_parse_and_count_diagnostics_together():
    res = validate("6 fM in MR\nwirr wirr\n6x zun (13)", dialect="de")
    assert [d.code for d in res.diagnostics] == ["W_PROSE", "E_COUNT_MISMATCH"]
    assert res.rows == [
        {"number": 1, "kind": "round", "actual": 6, "expected": None, "line": 1},
        {"number": 2, "kind": "round", "actual": 12, "expected": 13, "line": 3},
    ]
    assert not res.ok


def test_validate_reference_sphere_is_ok_and_fast():
    text = reference_pattern("3-sphere")
    validate(text)  # warm grammar cache
    t0 = time.perf_counter()
    res = validate(text)
    assert time.perf_counter() - t0 < 0.1
    assert res.ok
    assert res.total_stitches == 432

import pytest
from conftest import REFERENCE_DIR
from stitchcraft_core.gate import measure, write_report

pytestmark = pytest.mark.slow


def test_gate_measures_every_automated_criterion():
    m = measure(REFERENCE_DIR)
    assert set(m) == {"A1", "A2", "A3", "A4", "A5", "A6", "A7", "A8", "A9"}
    assert m["A3"]["status"] == "pass"
    assert m["A8"]["status"] == "pass"
    assert m["A1"]["status"] == "pending"  # no photos yet
    assert m["A6"]["status"] == "pending"  # manual blind test


def test_report_is_markdown_table(tmp_path):
    out = tmp_path / "m1.md"
    text = write_report(REFERENCE_DIR, out)
    assert out.read_text(encoding="utf-8") == text
    assert "| A5 |" in text and "Go/No-Go" in text

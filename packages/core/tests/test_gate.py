import pytest
from conftest import CORPUS_DIR, REFERENCE_DIR
from stitchcraft_core.gate import M5_EXTRA, M5_PIECE, measure, measure_m5, write_report

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


def test_report_carries_recorded_decision(tmp_path):
    out = tmp_path / "m1.md"
    (tmp_path / "m1-decision.md").write_text("Go ohne Fotos (2026-11-21).\n", encoding="utf-8")
    text = write_report(REFERENCE_DIR, out)
    assert "Go ohne Fotos (2026-11-21)." in text
    assert "Entscheidung erst" not in text


@pytest.fixture(scope="module")
def m5_report(tmp_path_factory):
    out = tmp_path_factory.mktemp("eval") / "m5.md"
    (out.parent / "m5-notes.md").write_text("V-Köpfe erkennbar.\n", encoding="utf-8")
    return write_report(REFERENCE_DIR, out, "m5", CORPUS_DIR)


def test_m5_gate_passes_for_tall_stitches():
    m = measure_m5(REFERENCE_DIR)
    assert set(m) == {"A3", "A4", "A5", "A7", "A8", "A9"}
    assert all(v["status"] == "pass" for v in m.values()), m
    assert set(m["A5"]["value"]) == {M5_PIECE, *M5_EXTRA}


def test_m5_report_has_corpus_table_and_notes(m5_report):
    assert m5_report.startswith("# M5-Abnahme")
    assert "| A7 | pass |" in m5_report
    assert "| en-UK/10-tr2tog |" in m5_report
    assert "| de/04-quadrat |" not in m5_report  # sc only
    assert "## Sichtprüfung" in m5_report and "V-Köpfe erkennbar." in m5_report

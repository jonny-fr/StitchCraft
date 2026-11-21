import json

from stitchcraft_core.cli import main


def test_validate_prints_json_diagnostics(tmp_path, capsys):
    f = tmp_path / "p.txt"
    f.write_text("6 fM in MR\n6x zun (13)\n", encoding="utf-8")
    code = main(["validate", str(f), "--dialect", "de"])
    out = json.loads(capsys.readouterr().out)
    assert code == 1
    assert out["diagnostics"][0]["code"] == "E_COUNT_MISMATCH"
    assert out["rows"][1]["actual"] == 12


def test_preview_writes_outputs(tmp_path):
    f = tmp_path / "p.txt"
    f.write_text("6 fM in MR (6)\n6x zun (12)\n", encoding="utf-8")
    out = tmp_path / "out"
    assert main(["preview", str(f), "--out", str(out)]) == 0
    assert {p.name for p in out.iterdir()} == {"yarn.bin", "model.glb", "shape.json"}


def test_preview_without_stitches_exits_with_diagnostics(tmp_path, capsys):
    f = tmp_path / "p.txt"
    f.write_text("nur Prosa\n", encoding="utf-8")
    assert main(["preview", str(f), "--out", str(tmp_path / "out")]) == 1
    assert json.loads(capsys.readouterr().err)["diagnostics"][0]["code"] == "W_PROSE"

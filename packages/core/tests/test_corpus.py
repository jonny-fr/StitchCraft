"""Golden corpus: tests/corpus/<dialect>/<name>.txt -> snapshot <name>.json.

Regenerate after an intended change with ``UPDATE_GOLDEN=1 uv run pytest -k corpus`` and
review the diff of the .json files.
"""

import json
import os
import time
from pathlib import Path

import pytest
from stitchcraft_core.notation import parse
from stitchcraft_core.notation.printer import format_pattern
from stitchcraft_core.pipeline import normalised_ir
from stitchcraft_core.validate import validate

CORPUS = Path(__file__).resolve().parents[3] / "tests" / "corpus"
FILES = sorted(CORPUS.glob("*/*.txt"))
ids = [f"{f.parent.name}/{f.stem}" for f in FILES]


def snapshot(text: str) -> dict:
    res = validate(text, dialect="auto")
    return {
        "dialect": res.dialect,
        "ok": res.ok,
        "stitches": res.total_stitches,
        "rows": [[r["number"], r["kind"], r["actual"], r["expected"]] for r in res.rows],
        "diagnostics": [
            {
                "code": d.code,
                "severity": d.severity,
                "line": d.span.line if d.span else None,
                "params": d.params,
            }
            for d in res.diagnostics
        ],
    }


def test_corpus_is_large_enough():
    per_dialect = {d: len(list((CORPUS / d).glob("*.txt"))) for d in ("de", "en-US", "en-UK")}
    assert sum(per_dialect.values()) >= 30
    assert min(per_dialect.values()) >= 10


@pytest.mark.parametrize("path", FILES, ids=ids)
def test_golden_snapshot(path: Path):
    got = snapshot(path.read_text(encoding="utf-8"))
    golden = path.with_suffix(".json")
    if os.environ.get("UPDATE_GOLDEN"):
        golden.write_text(json.dumps(got, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    assert got == json.loads(golden.read_text(encoding="utf-8"))


@pytest.mark.parametrize("path", FILES, ids=ids)
def test_detected_dialect_is_the_folder(path: Path):
    text = path.read_text(encoding="utf-8")
    res = parse(text, dialect="auto")
    ambiguous = any(d.code == "W_AMBIGUOUS_DIALECT" for d in res.diagnostics)
    assert res.pattern.dialect == path.parent.name or ambiguous


@pytest.mark.parametrize("path", FILES, ids=ids)
def test_corpus_roundtrips_through_printer(path: Path):
    dialect = path.parent.name
    pattern = parse(path.read_text(encoding="utf-8"), dialect=dialect).pattern
    again = parse(format_pattern(pattern, dialect), dialect=dialect).pattern
    assert normalised_ir(again) == normalised_ir(pattern)


def test_validate_is_fast_enough_for_live_lint():
    texts = [f.read_text(encoding="utf-8") for f in FILES]
    for t in texts:
        validate(t, dialect="auto")  # warm the grammar caches
    worst = 0.0
    for t in texts:
        t0 = time.perf_counter()
        validate(t, dialect="auto")
        worst = max(worst, time.perf_counter() - t0)
    assert worst < 0.1

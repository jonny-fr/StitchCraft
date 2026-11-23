"""Every diagnostic code, hover term and progress stage the UI shows has text in every UI language."""

import json
import re
from pathlib import Path

import pytest
from stitchcraft_core.ir import DIAGNOSTIC_CODES
from stitchcraft_core.notation.dialect import available_dialects, vocabulary

ROOT = Path(__file__).resolve().parents[3]
CORE = ROOT / "packages" / "core" / "src" / "stitchcraft_core"
LOCALES = ROOT / "web" / "src" / "i18n" / "locales"
LANGS = ("de", "en")
STAGES = {"queued", "validate", "shape", "yarn", "export", "done"}  # api.app jobs + final event


def catalog(lang: str) -> dict:
    return json.loads((LOCALES / f"{lang}.json").read_text(encoding="utf-8"))


def emitted_codes() -> set[str]:
    codes = set()
    for f in CORE.rglob("*.py"):
        codes |= set(re.findall(r'Diagnostic\(\s*"([EWI]_[A-Z_]+)"', f.read_text(encoding="utf-8")))
    return codes


def test_core_emits_only_declared_codes():
    emitted = emitted_codes()
    assert {"E_SYNTAX", "W_PROSE", "E_COUNT_MISMATCH", "E_TOO_FEW_PARENTS"} <= emitted
    assert emitted == DIAGNOSTIC_CODES


@pytest.mark.parametrize("lang", LANGS)
def test_every_code_has_text(lang):
    texts = catalog(lang)["diagnostics"]
    assert set(texts) == DIAGNOSTIC_CODES
    assert all(texts.values())


@pytest.mark.parametrize("lang", LANGS)
def test_every_progress_stage_has_text(lang):
    assert STAGES <= set(catalog(lang)["app"]["stage"])


@pytest.mark.parametrize("lang", LANGS)
def test_every_hover_word_is_described(lang):
    # mirrors App.describe: terms.<canonical>, else categories.<category>
    c = catalog(lang)
    for dialect in available_dialects():
        for w in vocabulary(dialect):
            assert w["canonical"] in c["terms"] or w["category"] in c["categories"], (dialect, w)

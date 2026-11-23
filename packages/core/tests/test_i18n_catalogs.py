"""Every diagnostic code, hover term and progress stage has text in every UI language."""

import json
import re
import tomllib
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
    assert set(catalog(lang)["app"]["stage"]) >= STAGES


@pytest.mark.parametrize("lang", LANGS)
def test_every_hover_word_is_described(lang):
    # mirrors App.describe: terms.<canonical>, else categories.<category>
    c = catalog(lang)
    for dialect in available_dialects():
        for w in vocabulary(dialect):
            assert w["canonical"] in c["terms"] or w["category"] in c["categories"], (dialect, w)


def server_catalog(lang: str) -> dict:
    return tomllib.loads((ROOT / "data" / "messages" / f"{lang}.toml").read_text(encoding="utf-8"))


@pytest.mark.parametrize("lang", LANGS)
def test_server_diagnostic_texts_match_web(lang):
    # the MCP server answers with the same sentences the UI shows; any drift fails here
    assert server_catalog(lang)["diagnostics"] == catalog(lang)["diagnostics"]


@pytest.mark.parametrize("lang", LANGS)
def test_server_catalog_has_no_unknown_placeholders(lang):
    allowed = {"line", "row", "actual", "expected", "needed", "available", "left", "limit"} | {
        "name",
        "candidates",
        "chosen",
        "abbr",
        "meaning",
    }
    for text in server_catalog(lang)["diagnostics"].values():
        assert set(re.findall(r"\{\{(\w+)\}\}", text)) <= allowed


def test_diagnostic_message_fills_placeholders_and_survives_missing_ones():
    from stitchcraft_core.messages import diagnostic_message, message

    full = diagnostic_message("E_COUNT_MISMATCH", {"row": 2, "actual": 5, "expected": 6}, 3, "en")
    assert full == "Round/row 2: counted 5 stitches, pattern says 6."
    assert "{{row}}" in diagnostic_message("W_UNWORKED", {}, None, "de")  # no crash
    assert diagnostic_message(
        "W_AMBIGUOUS_DIALECT", {"candidates": ["a", "b"], "chosen": "a"}, None, "en"
    )
    assert message("snapshot.unavailable", "de") and message("snapshot.unavailable", "en")
    with pytest.raises(ValueError, match="unknown locale"):
        message("snapshot.unavailable", "fr")

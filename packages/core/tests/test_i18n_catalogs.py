"""Every diagnostic code the core can emit has a message in every UI language."""

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CORE = ROOT / "packages" / "core" / "src" / "stitchcraft_core"
LOCALES = ROOT / "web" / "src" / "i18n" / "locales"


def emitted_codes() -> set[str]:
    codes = set()
    for f in CORE.rglob("*.py"):
        codes |= set(re.findall(r'Diagnostic\(\s*"([EWI]_[A-Z_]+)"', f.read_text(encoding="utf-8")))
    return codes


def test_core_emits_known_codes():
    assert {"E_SYNTAX", "W_PROSE", "E_COUNT_MISMATCH", "E_TOO_FEW_PARENTS"} <= emitted_codes()


def test_every_code_has_de_and_en_text():
    codes = emitted_codes()
    for lang in ("de", "en"):
        catalog = json.loads((LOCALES / f"{lang}.json").read_text(encoding="utf-8"))
        missing = codes - set(catalog["diagnostics"])
        assert not missing, f"{lang}: {sorted(missing)}"

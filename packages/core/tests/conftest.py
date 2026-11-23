from pathlib import Path

import pytest

REFERENCE_DIR = Path(__file__).resolve().parents[3] / "tests" / "reference"
CORPUS_DIR = REFERENCE_DIR.parent / "corpus"
PIECES = ["1-square", "2-disc", "3-sphere", "4-cup", "5-hyperbolic"]


def reference_pattern(piece: str) -> str:
    return (REFERENCE_DIR / piece / "pattern.txt").read_text(encoding="utf-8")


@pytest.fixture(params=PIECES)
def piece(request) -> str:
    return request.param

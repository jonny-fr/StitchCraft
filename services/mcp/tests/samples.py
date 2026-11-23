from pathlib import Path

CORPUS = Path(__file__).resolve().parents[3] / "tests" / "corpus"
TINY = "Rd. 1: 6 fM in MR (6)\nRd. 2: 6x zun (12)"


def corpus(dialect: str, name: str) -> str:
    return (CORPUS / dialect / name).read_text(encoding="utf-8")

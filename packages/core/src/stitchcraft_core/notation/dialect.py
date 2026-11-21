"""Dialect profiles: vocabulary tables loaded from data/dialects/*.toml."""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import cache

from stitchcraft_core.data import data_dir, load_toml

CATEGORIES = ("stitches", "macros", "loops")


def normalise(word: str) -> str:
    return re.sub(r"\s+", "", word).casefold()


def word_regex(words: list[str], digit_follows: bool = False) -> str:
    """Case-insensitive alternation, longest first, with word boundaries at word chars.

    ``digit_follows`` lets a digit touch the word ("R1", "Rd1")."""
    end = r"(?![^\W\d])" if digit_follows else r"(?!\w)"
    parts = []
    for w in sorted(set(words), key=len, reverse=True):
        p = r"\s*".join(re.escape(tok) for tok in w.split())
        if w[0].isalnum():
            p = r"(?<!\w)" + p
        if w[-1].isalnum():
            p = p + end
        parts.append(p)
    return "(?:" + "|".join(parts) + ")"


@dataclass(frozen=True)
class Dialect:
    id: str
    name: str
    turning_chain_counts: bool
    lookup: dict[str, tuple[str, str]]  # normalised word -> (category, canonical)
    words: dict[str, list[str]]  # terminal name -> words

    def canonical(self, word: str) -> str:
        return self.lookup[normalise(word)][1]


def available_dialects() -> list[str]:
    return sorted(p.stem for p in (data_dir() / "dialects").glob("*.toml"))


@cache
def load_dialect(dialect_id: str) -> Dialect:
    if dialect_id not in available_dialects():
        raise ValueError(f"unknown dialect {dialect_id!r}")
    raw = load_toml("dialects", f"{dialect_id}.toml")
    lookup: dict[str, tuple[str, str]] = {}
    words: dict[str, list[str]] = {}
    for terminal, category in (("STITCH", "stitches"), ("MACRO", "macros"), ("LOOPMOD", "loops")):
        words[terminal] = []
        for canonical, variants in raw[category].items():
            for v in variants:
                lookup[normalise(v)] = (category, canonical)
                words[terminal].append(v)
    kw = raw["keywords"]
    words["RING"] = kw["ring"]
    words["TURN"] = kw["turn"]
    words["EACH"] = kw["each"]
    words["LABEL"] = kw["round_label"] + kw["row_label"] + kw["row_label_short"]
    words["IGNORED"] = kw["ignored"]
    for v in kw["round_label"]:
        lookup[normalise(v)] = ("label", "round")
    for v in kw["row_label"]:
        lookup[normalise(v)] = ("label", "row")
    for v in kw["row_label_short"]:
        lookup[normalise(v)] = ("label", "short")  # round or row, decided from context
    meta = raw["meta"]
    return Dialect(
        id=meta["id"],
        name=meta["name"],
        turning_chain_counts=meta.get("turning_chain_counts", False),
        lookup=lookup,
        words=words,
    )

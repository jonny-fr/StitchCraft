"""Dialect profiles: vocabulary tables loaded from data/dialects/*.toml."""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from functools import cache

from stitchcraft_core.data import data_dir, load_toml

CATEGORIES = ("stitches", "macros", "loops")
TERMINALS = {"stitches": "STITCH", "macros": "MACRO", "loops": "LOOPMOD"}


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

    def with_aliases(self, aliases: tuple[tuple[str, str, str], ...]) -> Dialect:
        """Copy with extra (word, category, canonical) vocabulary, e.g. from a glossary block.

        An alias replaces any meaning the word had before."""
        lookup = dict(self.lookup)
        words = {k: list(v) for k, v in self.words.items()}
        for word, category, canonical in aliases:
            key = normalise(word)
            for terminal in TERMINALS.values():
                words[terminal] = [w for w in words[terminal] if normalise(w) != key]
            lookup[key] = (category, canonical)
            words[TERMINALS[category]].append(word)
        return replace(self, lookup=lookup, words=words)


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
    words["CHANGE"] = kw["color_change"]
    words["PALETTE"] = kw["palette"]
    words["GLOSSARY"] = kw.get("glossary", [])
    words["SAME"] = kw.get("same", [])
    words["SKIP"] = kw.get("skip", [])
    words["STW"] = kw.get("stitch_word", [])
    words["TOGETHER"] = kw.get("together", [])
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


# keyword table -> category reported to the editor (highlighting, hover)
KEYWORD_CATEGORIES = {
    "round_label": "label",
    "row_label": "label",
    "row_label_short": "label",
    "ring": "ring",
    "turn": "turn",
    "each": "each",
    "same": "same",
    "skip": "skip",
    "stitch_word": "stitch_word",
    "together": "together",
    "color_change": "color_change",
    "palette": "palette",
    "glossary": "glossary",
    "ignored": "ignored",
}


def vocabulary(dialect_id: str) -> list[dict[str, str]]:
    """Every word of a dialect with its category and canonical meaning."""
    if dialect_id not in available_dialects():
        raise ValueError(f"unknown dialect {dialect_id!r}")
    raw = load_toml("dialects", f"{dialect_id}.toml")
    out = []
    for category, singular in (("stitches", "stitch"), ("macros", "macro"), ("loops", "loop")):
        for canonical, variants in raw[category].items():
            out += [{"word": v, "category": singular, "canonical": canonical} for v in variants]
    for key, category in KEYWORD_CATEGORIES.items():
        canonical = {"round_label": "round", "row_label": "row"}.get(key, key)
        out += [
            {"word": v, "category": category, "canonical": canonical}
            for v in raw["keywords"].get(key, [])
        ]
    return out

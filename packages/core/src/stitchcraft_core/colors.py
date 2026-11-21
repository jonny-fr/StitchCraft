"""Yarn colours: colour names from data/colors.toml, palette codes, fallback colours."""

from __future__ import annotations

import re
from functools import cache

from stitchcraft_core.data import load_toml

HEX = re.compile(r"#[0-9a-fA-F]{6}")
CODE = r"[A-Z][A-Z0-9]{0,3}"  # A, B, MC, CC1, ...


def name_key(word: str) -> str:
    return " ".join(word.split()).casefold()


@cache
def names() -> dict[str, str]:
    """Colour name (any language, normalised) -> "#rrggbb"."""
    raw = load_toml("colors.toml")
    return {name_key(n): hex_.lower() for hex_, ns in raw["names"].items() for n in ns}


def defaults() -> list[str]:
    return list(load_toml("colors.toml")["defaults"])


def ref(token: str) -> str:
    """Canonical colour reference for a word from the pattern text."""
    if HEX.fullmatch(token):
        return token.lower()
    key = name_key(token)
    return key if key in names() else token


def known_hex(color: str) -> str | None:
    """Hex for a colour name or "#rrggbb", None for codes and unknown words."""
    if HEX.fullmatch(color):
        return color.lower()
    return names().get(name_key(color))


def resolve(used: list[str], palette: dict[str, str | None]) -> list[dict[str, object]]:
    """Hex per used colour; colours the pattern leaves open get the fallbacks in order."""
    fallback = iter(defaults())
    out = []
    for color in used:
        hex_ = palette.get(color) or known_hex(color)
        out.append(
            {"ref": color, "hex": hex_ or next(fallback, "#efe6d2"), "defined": hex_ is not None}
        )
    return out

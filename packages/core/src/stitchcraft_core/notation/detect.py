"""Guess the dialect of a pattern from marker words in data/dialects/*.toml ([detect]).

The language is decided first (German vs English vocabulary), then the dialect within it.
US and UK share ch/dc/tr with different meanings, so a pattern using only those is
reported as ambiguous instead of silently assuming one.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import cache

from stitchcraft_core.data import load_toml
from stitchcraft_core.notation.dialect import available_dialects, word_regex

DEFAULT = "de"


@dataclass(frozen=True)
class Detection:
    dialect: str
    ambiguous: bool = False
    candidates: list[str] = field(default_factory=list)
    scores: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class _Profile:
    id: str
    language: str
    priority: int
    markers: re.Pattern[str] | None
    language_markers: re.Pattern[str] | None


def _compile(words: list[str]) -> re.Pattern[str] | None:
    return re.compile(word_regex(words), re.IGNORECASE) if words else None


@cache
def _profiles() -> list[_Profile]:
    out = []
    for d in available_dialects():
        raw = load_toml("dialects", f"{d}.toml")["detect"]
        out.append(
            _Profile(
                d,
                raw["language"],
                raw.get("priority", 0),
                _compile(raw["markers"]),
                _compile(raw.get("language_markers", [])),
            )
        )
    return sorted(out, key=lambda p: (p.language, p.priority))


def _count(rx: re.Pattern[str] | None, text: str) -> int:
    return len(rx.findall(text)) if rx else 0


def detect_dialect(text: str) -> Detection:
    profiles = _profiles()
    own = {p.id: _count(p.markers, text) for p in profiles}
    languages: dict[str, int] = {}
    shared_seen: set[str] = set()
    for p in profiles:
        languages[p.language] = languages.get(p.language, 0) + own[p.id]
        if p.language not in shared_seen:  # shared markers count once per language
            languages[p.language] += _count(p.language_markers, text)
            shared_seen.add(p.language)
    if not any(languages.values()):
        return Detection(DEFAULT, scores=own)
    language = max(languages, key=lambda lang: (languages[lang], lang == DEFAULT))
    group = [p for p in profiles if p.language == language]
    best = max(own[p.id] for p in group)
    winners = [p.id for p in group if own[p.id] == best]
    if len(winners) == 1:
        return Detection(winners[0], scores=own)
    return Detection(winners[0], ambiguous=True, candidates=winners, scores=own)

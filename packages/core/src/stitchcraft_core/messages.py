"""Localised texts for server-side consumers (MCP); the web UI keeps its own catalogs."""

from __future__ import annotations

import re
from typing import Any

from stitchcraft_core.data import load_toml

LOCALES = ("de", "en")
_PLACEHOLDER = re.compile(r"\{\{(\w+)\}\}")


def _fill(template: str, values: dict[str, Any]) -> str:
    def one(m: re.Match[str]) -> str:
        value = values.get(m.group(1))
        if value is None:
            return m.group(0)  # a missing value stays visible instead of crashing
        return ", ".join(map(str, value)) if isinstance(value, list | tuple) else str(value)

    return _PLACEHOLDER.sub(one, template)


def _catalog(locale: str) -> dict[str, Any]:
    if locale not in LOCALES:
        raise ValueError(f"unknown locale {locale!r}; use one of {', '.join(LOCALES)}")
    return load_toml("messages", f"{locale}.toml")


def diagnostic_message(code: str, params: dict[str, Any], line: int | None, locale: str) -> str:
    """Text for a diagnostic (`code`, `params`, source `line`) in `locale`; the line goes in as
    `{{line}}` like in the web UI."""
    template = _catalog(locale)["diagnostics"].get(code, code)
    return _fill(template, {**params, "line": line})


def message(key: str, locale: str, **values: Any) -> str:
    """`key` is `section.name`, e.g. `snapshot.unavailable`; `values` fill `{{placeholders}}`."""
    section, name = key.split(".", 1)
    return _fill(str(_catalog(locale)[section][name]), values)

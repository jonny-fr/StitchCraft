"""Locates the versioned data directory (dialects, stitch library)."""

from __future__ import annotations

import os
import tomllib
from functools import cache
from pathlib import Path
from typing import Any


@cache
def data_dir() -> Path:
    env = os.environ.get("STITCHCRAFT_DATA")
    if env:
        return Path(env)
    for parent in Path(__file__).resolve().parents:
        candidate = parent / "data"
        if (candidate / "dialects").is_dir():
            return candidate
    raise FileNotFoundError("Stitchcraft data directory not found; set STITCHCRAFT_DATA")


@cache
def load_toml(*parts: str) -> dict[str, Any]:
    with (data_dir().joinpath(*parts)).open("rb") as f:
        return tomllib.load(f)

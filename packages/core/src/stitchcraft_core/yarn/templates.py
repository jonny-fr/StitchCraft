"""Parametric yarn templates per stitch type, loaded from data/stitches/templates.toml."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache

import numpy as np

from stitchcraft_core.data import load_toml


@dataclass(frozen=True)
class Template:
    points: np.ndarray  # (K, 3) u, v, n
    anchors: np.ndarray  # (K,) 0 own base, 1/2 parent tops


@cache
def template_for(stitch: str, loop: str = "both") -> Template:
    raw = load_toml("stitches", "templates.toml")
    entry = raw.get(stitch) or raw["sc"]
    variant = entry.get(loop) or entry["both"]
    arr = np.array(variant["points"], dtype=float)
    return Template(arr[:, :3], arr[:, 3].astype(int))


def templates_version() -> int:
    return int(load_toml("stitches", "templates.toml")["version"])

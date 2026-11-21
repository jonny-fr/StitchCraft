"""Execution parameters the pattern does not state (yarn, hook, gauge, stuffing, ...)."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Literal

from stitchcraft_core.data import load_toml


@dataclass(frozen=True)
class Params:
    yarn_mm: float = 2.0
    hook_mm: float = 3.5
    gauge_stitches: float | None = None  # sc per 10 cm
    gauge_rows: float | None = None  # sc rows per 10 cm
    fill: float = 0.7  # stuffing 0..1, closed shapes only
    handedness: Literal["right", "left"] = "right"
    right_side_out: bool = True
    material: Literal["cotton", "acrylic", "mohair"] = "cotton"
    color: str = "#efe6d2"
    seed: int = 0

    @property
    def stitch_width_mm(self) -> float:
        if self.gauge_stitches:
            return 100.0 / self.gauge_stitches
        return self.hook_mm * library()["gauge_defaults"]["width_per_hook_mm"]

    @property
    def row_height_mm(self) -> float:
        if self.gauge_rows:
            return 100.0 / self.gauge_rows
        return self.hook_mm * library()["gauge_defaults"]["height_per_hook_mm"]

    @property
    def yarn_radius_mm(self) -> float:
        return self.yarn_mm / 2.0

    def stitch_size(self, stitch_type: str) -> tuple[float, float]:
        """(width, height) in mm of one stitch of the given canonical type."""
        entry = library()["stitch"].get(stitch_type, library()["stitch"]["sc"])
        return entry["width"] * self.stitch_width_mm, entry["height"] * self.row_height_mm

    def cache_key(self) -> str:
        blob = json.dumps({"params": asdict(self), "library": library()["version"]}, sort_keys=True)
        return hashlib.sha256(blob.encode()).hexdigest()


def library() -> dict:
    return load_toml("stitches", "library.toml")

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator
from stitchcraft_core.notation.dialect import available_dialects


class PatternIn(BaseModel):
    text: str = Field(max_length=200_000)
    dialect: str = "de"

    @field_validator("dialect")
    @classmethod
    def known_dialect(cls, v: str) -> str:
        if v not in available_dialects():
            raise ValueError(f"unknown dialect {v!r}")
        return v


class ParamsIn(BaseModel):
    yarn_mm: float = Field(2.0, gt=0.3, lt=15)
    hook_mm: float = Field(3.5, gt=0.5, lt=25)
    gauge_stitches: float | None = Field(None, gt=1, lt=100)
    gauge_rows: float | None = Field(None, gt=1, lt=100)
    fill: float = Field(0.7, ge=0, le=1)
    handedness: Literal["right", "left"] = "right"
    right_side_out: bool = True
    material: Literal["cotton", "acrylic", "mohair"] = "cotton"
    color: str = Field("#efe6d2", pattern=r"^#[0-9a-fA-F]{6}$")
    seed: int = 0


class PreviewIn(PatternIn):
    params: ParamsIn = Field(default_factory=ParamsIn)

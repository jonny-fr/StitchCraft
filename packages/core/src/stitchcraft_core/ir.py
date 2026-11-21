"""Canonical, dialect-neutral pattern model.

Stitch types use US terminology as canonical ids (ch, slst, sc, hdc, dc, tr);
dialect tables map their own vocabulary onto these.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Literal


class Loop(StrEnum):
    BOTH = "both"
    BLO = "blo"
    FLO = "flo"


@dataclass(frozen=True)
class SourceSpan:
    start: int  # absolute char offset
    end: int
    line: int  # 1-based
    col: int  # 1-based


@dataclass(frozen=True)
class Diagnostic:
    code: str
    severity: Literal["error", "warning", "info"]
    span: SourceSpan | None = None
    params: dict[str, object] = field(default_factory=dict)


@dataclass
class Stitch:
    type: str
    count: int = 1
    loop: Loop = Loop.BOTH
    into_ring: bool = False
    span: SourceSpan | None = None


@dataclass
class Macro:
    kind: Literal["inc", "dec"]
    count: int = 1
    loop: Loop = Loop.BOTH
    stitch: str = "sc"
    span: SourceSpan | None = None


@dataclass
class Each:
    """``count`` stitches into every remaining stitch of the previous row ("sc around")."""

    type: str
    count: int = 1
    loop: Loop = Loop.BOTH
    span: SourceSpan | None = None


@dataclass
class Turn:
    span: SourceSpan | None = None


@dataclass
class Repeat:
    body: list[Instruction]
    times: int
    span: SourceSpan | None = None


Instruction = Stitch | Macro | Each | Turn | Repeat


@dataclass
class Row:
    number: int
    kind: Literal["round", "row"]
    instructions: list[Instruction]
    expected_count: int | None = None
    span: SourceSpan | None = None


@dataclass
class Part:
    rows: list[Row] = field(default_factory=list)


@dataclass
class Pattern:
    dialect: str
    parts: list[Part] = field(default_factory=list)

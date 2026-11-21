"""IR rows -> flat operation sequences (repeats and macros resolved)."""

from __future__ import annotations

from dataclasses import dataclass

from stitchcraft_core.ir import (
    ColorChange,
    Each,
    Instruction,
    Into,
    Loop,
    Macro,
    Repeat,
    Row,
    Skip,
    SourceSpan,
    Stitch,
    Turn,
)

MAX_TURNING_CHAIN = 3
MAX_STITCHES = 5_000  # preview costs ~7 ms per stitch, so this caps a request at ~35 s


@dataclass
class Op:
    type: str
    consume: int = 1  # how many new parent stitches this op works into
    share: bool = False  # works into the same stitch as the previous op
    ring: bool = False
    counting: bool = True
    turning: bool = False
    macro: str | None = None
    loop: Loop = Loop.BOTH
    span: SourceSpan | None = None


@dataclass
class EachOp:
    type: str
    count: int = 1
    loop: Loop = Loop.BOTH
    span: SourceSpan | None = None


@dataclass
class TurnOp:
    span: SourceSpan | None = None


@dataclass
class ColorOp:
    color: str


@dataclass
class SkipOp:
    count: int


RowOp = Op | EachOp | TurnOp | ColorOp | SkipOp


def _ops(instr: Instruction) -> list[RowOp]:
    match instr:
        case Stitch(type=t, count=n, loop=loop, into_ring=ring, span=span):
            consume = 0 if (ring or t == "ch") else 1
            return [Op(t, consume, ring=ring, loop=loop, span=span) for _ in range(n)]
        case Macro(kind="inc", count=n, loop=loop, stitch=t, span=span):
            return [
                op
                for _ in range(n)
                for op in (
                    Op(t, 1, macro="inc", loop=loop, span=span),
                    Op(t, 0, share=True, macro="inc", loop=loop, span=span),
                )
            ]
        case Macro(kind="dec", count=n, loop=loop, stitch=t, merge=k, span=span):
            return [Op(t, k, macro="dec", loop=loop, span=span) for _ in range(n)]
        case Into(body=body):
            ops = [op for i in body for op in _ops(i)]
            made = [op for op in ops if isinstance(op, Op) and op.consume > 0]
            for k, op in enumerate(made):
                op.consume, op.share = (1, False) if k == 0 else (0, True)
                if len(made) > 1 and op.macro is None:
                    op.macro = "inc"
            return ops
        case Skip(count=n):
            return [SkipOp(n)]
        case Each(type=t, count=n, loop=loop, span=span):
            return [EachOp(t, n, loop, span)]
        case Turn(span=span):
            return [TurnOp(span)]
        case ColorChange(color=color):
            return [ColorOp(color)]
        case Repeat(body=body, times=times):
            return [op for _ in range(times) for i in body for op in _ops(i)]
    raise TypeError(f"unknown instruction {instr!r}")


def size(instrs: list[Instruction], parents: int) -> int:
    """Upper bound of the ops a row expands to, computed without expanding it."""
    total = 0
    for instr in instrs:
        match instr:
            case Stitch(count=n) | Macro(kind="dec", count=n):
                total += n
            case Macro(count=n):
                total += 2 * n
            case Each(count=n):
                total += n * parents
            case Into(body=body):
                total += size(body, parents)
            case Repeat(body=body, times=times):
                total += times * size(body, parents)
    return total


def pattern_size(rows: list[Row]) -> int:
    total = prev = 0
    for row in rows:
        prev = size(row.instructions, prev)
        total += prev
        if total > MAX_STITCHES:
            break
    return total


def expand_row(row: Row) -> list[RowOp]:
    ops = [op for instr in row.instructions for op in _ops(instr)]
    _mark_turning_chains(ops)
    return ops


def _mark_turning_chains(ops: list[RowOp]) -> None:
    """Short chain runs at the row start or right before a turn are turning chains."""
    is_ch = [isinstance(o, Op) and o.type == "ch" for o in ops]
    stitches = [c for c, o in zip(is_ch, ops, strict=True) if isinstance(o, Op | EachOp)]
    if all(stitches) or not any(stitches):
        return
    runs: list[tuple[int, int]] = []
    i = 0
    while i < len(ops):
        if is_ch[i]:
            j = i
            while j < len(ops) and is_ch[j]:
                j += 1
            runs.append((i, j))
            i = j
        else:
            i += 1
    for start, end in runs:
        at_start = all(isinstance(o, ColorOp) for o in ops[:start])
        after = next((o for o in ops[end:] if not isinstance(o, ColorOp)), None)
        before_turn = after is None or isinstance(after, TurnOp)
        if (at_start or before_turn) and end - start <= MAX_TURNING_CHAIN:
            for k in range(start, end):
                op = ops[k]
                assert isinstance(op, Op)
                op.counting = False
                op.turning = True

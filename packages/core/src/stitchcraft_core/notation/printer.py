"""Canonical IR -> pattern text in a dialect (the inverse of the parser).

Spellings come from the [print] table of the dialect file, falling back to the first
variant of each vocabulary entry. parse(format_pattern(p, d), d) reproduces p.
"""

from __future__ import annotations

from functools import cache

from stitchcraft_core.data import load_toml
from stitchcraft_core.ir import (
    ColorChange,
    Each,
    Instruction,
    Into,
    Loop,
    Macro,
    Pattern,
    Repeat,
    Row,
    Skip,
    Stitch,
    Turn,
)


class _Words:
    def __init__(self, dialect: str):
        raw = load_toml("dialects", f"{dialect}.toml")
        self.raw = raw
        self.pref = raw.get("print", {})
        kw = raw["keywords"]
        self.kw = kw

    def get(self, key: str, fallback: list[str]) -> str:
        return self.pref.get(key) or fallback[0]

    def stitch(self, t: str) -> str:
        return self.raw["stitches"][t][0]

    def macro(self, kind: str) -> str:
        return self.raw["macros"][kind][0]

    def loop(self, loop: Loop) -> str:
        return self.get(str(loop), self.raw["loops"][str(loop)])

    def keyword(self, key: str) -> str:
        return self.get(key, self.kw[key])

    def label(self, kind: str) -> str:
        return self.get(kind, self.kw["round_label" if kind == "round" else "row_label"])


@cache
def _words(dialect: str) -> _Words:
    return _Words(dialect)


def _leaves(instrs: list[Instruction]):
    for i in instrs:
        if isinstance(i, Repeat | Into):
            yield from _leaves(i.body)
        elif isinstance(i, Stitch | Macro | Each):
            yield i


def _row_loop(row: Row) -> Loop | None:
    """The loop every stitch of the row shares, printed once in the label."""
    loops = {leaf.loop for leaf in _leaves(row.instructions)}
    if len(loops) == 1 and (loop := loops.pop()) is not Loop.BOTH:
        return loop
    return None


class _Printer:
    def __init__(self, dialect: str):
        self.w = _words(dialect)
        self.english = not dialect.startswith("de")
        self.row_loop: Loop | None = None

    def _loop(self, loop: Loop) -> str:
        return "" if loop is Loop.BOTH or loop is self.row_loop else " " + self.w.loop(loop)

    def instr(self, i: Instruction) -> str:
        w = self.w
        match i:
            case Stitch(type=t, count=n, loop=loop, into_ring=ring):
                out = f"{n} {w.stitch(t)}{self._loop(loop)}"
                return out + (f" {w.keyword('ring')}" if ring else "")
            case Macro(kind="dec", stitch=t, merge=k, count=n, loop=loop) if t != "sc" or k != 2:
                if self.english:
                    word = f"{w.stitch(t)}{k}tog"
                else:
                    word = f"{k} {w.stitch(t)} {w.keyword('together')}"
                return ", ".join([word + self._loop(loop)] * n)
            case Macro(kind="dec", count=n, loop=Loop.FLO) if self.row_loop is not Loop.FLO:
                return self._count(n, w.macro("invdec"))
            case Macro(kind=kind, count=n, loop=loop):
                return self._count(n, w.macro(kind)) + self._loop(loop)
            case Each(type=t, count=n, loop=loop):
                return f"{n} {w.stitch(t)}{self._loop(loop)} {w.keyword('each')}"
            case Turn():
                return w.keyword("turn")
            case ColorChange(color=c):
                return f"{w.keyword('color_change')} {c}"
            case Skip(count=n):
                if self.english:
                    return f"{w.keyword('skip')} {n}"
                return f"{n} {w.keyword('stitch_word')} {w.keyword('skip')}"
            case Into(body=[Stitch(type=t, count=n, loop=loop)]):
                return f"{n} {w.stitch(t)}{self._loop(loop)} {w.keyword('same')}"
            case Into(body=body):
                return f"({self.body(body)}) {w.keyword('same')}"
            case Repeat(body=[single], times=times) if not isinstance(single, Repeat):
                inner = self.instr(single)
                return f"({inner})" if times == 1 else f"{times}x {inner}"
            case Repeat(body=body, times=times):
                return f"({self.body(body)})" + ("" if times == 1 else f" x{times}")
        raise TypeError(f"cannot print {i!r}")

    @staticmethod
    def _count(n: int, word: str) -> str:
        return word if n == 1 else f"{n} {word}"

    def body(self, instrs: list[Instruction]) -> str:
        return ", ".join(self.instr(i) for i in instrs)

    def row(self, row: Row) -> str:
        self.row_loop = _row_loop(row)
        label = f"{self.w.label(row.kind)} {row.number}"
        if self.row_loop is not None:
            label += f" ({self.w.loop(self.row_loop)})"
        out = f"{label}: {self.body(row.instructions)}"
        if row.expected_count is not None:
            out += f" ({row.expected_count})"
        self.row_loop = None
        return out


def format_pattern(pattern: Pattern, dialect: str | None = None) -> str:
    dialect = dialect or pattern.dialect
    p = _Printer(dialect)
    lines = []
    if pattern.palette:
        entries = ", ".join(f"{code} = {hex_ or code}" for code, hex_ in pattern.palette.items())
        lines.append(f"{p.w.keyword('palette')}: {entries}")
    for part in pattern.parts:
        lines += [p.row(r) for r in part.rows]
    return "\n".join(lines)

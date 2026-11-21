"""Pattern text -> canonical IR.

One structural grammar for all dialects; the vocabulary terminals are filled in
from the dialect tables. Each line is parsed on its own so that a bad line does
not hide the rest of the pattern.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field
from functools import cache

from lark import Lark, Token, Transformer, v_args
from lark.exceptions import LarkError

from stitchcraft_core.ir import (
    Diagnostic,
    Each,
    Instruction,
    Loop,
    Macro,
    Part,
    Pattern,
    Repeat,
    Row,
    SourceSpan,
    Stitch,
    Turn,
)
from stitchcraft_core.notation.dialect import Dialect, load_dialect, normalise, word_regex

GRAMMAR = r"""
start: label? body count? "."?

label: LABEL range lmod? ":"
lmod: "(" LOOPMOD ")"
range: INT ("-" INT)?

body: element ("," element)* ","?
element: LOOPMOD? item times?       -> element
       | INT X LOOPMOD? item        -> prefix_repeat
       | RING                       -> ring_only

?item: stitch | macro | each | turn | group
stitch: INT? STITCH INT? LOOPMOD? RING?
macro: INT? MACRO LOOPMOD?
each: STITCH EACH | EACH INT? STITCH
turn: TURN
group: "(" body ")" | "[" body "]" | "*" body "*"
times: X INT | INT X
count: "(" INT ")"

INT: /\d+/
X: /[x×]/i
%import common.WS
%ignore WS
"""


@dataclass
class ParseResult:
    pattern: Pattern
    diagnostics: list[Diagnostic] = field(default_factory=list)


@cache
def _parser(dialect_id: str) -> Lark:
    d = load_dialect(dialect_id)
    terminals = "\n".join(
        f"{name}: /{word_regex(d.words[name])}/i"
        for name in ("STITCH", "MACRO", "LOOPMOD", "RING", "TURN", "EACH", "LABEL")
    )
    return Lark(
        GRAMMAR + terminals,
        parser="earley",
        lexer="dynamic",
        propagate_positions=True,
        ambiguity="resolve",
    )


@dataclass
class _LineCtx:
    offset: int
    line: int

    def span(self, start: int, end: int) -> SourceSpan:
        return SourceSpan(self.offset + start, self.offset + end, self.line, start + 1)


@dataclass
class _Element:
    instr: Instruction
    loop: Loop | None


@dataclass
class _Label:
    kind: str
    first: int
    last: int
    loop: Loop | None


@v_args(meta=True)
class _ToIR(Transformer):
    def __init__(self, dialect: Dialect, ctx: _LineCtx):
        super().__init__()
        self.d = dialect
        self.ctx = ctx

    def _span(self, meta) -> SourceSpan | None:
        if getattr(meta, "empty", True):
            return None
        return self.ctx.span(meta.start_pos, meta.end_pos)

    def _loop(self, tok: Token) -> Loop:
        return Loop(self.d.canonical(tok))

    @staticmethod
    def _split(children):
        ints = [c for c in children if isinstance(c, Token) and c.type == "INT"]
        toks = {c.type: c for c in children if isinstance(c, Token) and c.type != "INT"}
        return ints, toks

    def start(self, meta, children):
        label = next((c for c in children if isinstance(c, _Label)), None)
        body = next(c for c in children if isinstance(c, list))
        count = next((c for c in children if isinstance(c, int)), None)
        return label, body, count

    def label(self, meta, children):
        tok = children[0]
        first, last = children[1]
        loop = children[2] if len(children) > 2 else None
        return _Label(self.d.lookup[normalise(tok)][1], first, last, loop)

    def lmod(self, meta, children):
        return self._loop(children[0])

    def range(self, meta, children):
        nums = [int(c) for c in children]
        return nums[0], nums[-1]

    def body(self, meta, children):
        current: Loop | None = None
        out: list[Instruction] = []
        for el in children:
            if el.loop is not None:
                current = el.loop
            if current is not None:
                _apply_loop(el.instr, current)
            out.append(el.instr)
        return out

    def element(self, meta, children):
        loop = None
        rest = list(children)
        if isinstance(rest[0], Token) and rest[0].type == "LOOPMOD":
            loop = self._loop(rest.pop(0))
        instr = rest[0]
        if len(rest) > 1:
            if isinstance(instr, Repeat) and instr.times == 1:
                instr.times = rest[1]
                instr.span = self._span(meta)
            else:
                instr = Repeat(body=[instr], times=rest[1], span=self._span(meta))
        return _Element(instr, loop)

    def prefix_repeat(self, meta, children):
        times = int(children[0])
        rest = children[2:]
        loop = None
        if isinstance(rest[0], Token):
            loop = self._loop(rest.pop(0))
        return _Element(Repeat(body=[rest[0]], times=times, span=self._span(meta)), loop)

    def ring_only(self, meta, children):
        return _Element(Stitch(type="ring", count=0, into_ring=True, span=self._span(meta)), None)

    def stitch(self, meta, children):
        ints, toks = self._split(children)
        st = Stitch(
            type=self.d.canonical(toks["STITCH"]),
            count=int(ints[0]) if ints else 1,
            into_ring="RING" in toks,
            span=self._span(meta),
        )
        if "LOOPMOD" in toks:
            st.loop = self._loop(toks["LOOPMOD"])
        return st

    def macro(self, meta, children):
        ints, toks = self._split(children)
        m = Macro(
            kind=self.d.canonical(toks["MACRO"]),
            count=int(ints[0]) if ints else 1,
            span=self._span(meta),
        )
        if "LOOPMOD" in toks:
            m.loop = self._loop(toks["LOOPMOD"])
        return m

    def each(self, meta, children):
        _, toks = self._split(children)
        return Each(type=self.d.canonical(toks["STITCH"]), span=self._span(meta))

    def turn(self, meta, children):
        return Turn(span=self._span(meta))

    def group(self, meta, children):
        return Repeat(body=children[0], times=1, span=self._span(meta))

    def times(self, meta, children):
        return int(next(c for c in children if c.type == "INT"))

    def count(self, meta, children):
        return int(children[0])


def _apply_loop(instr: Instruction, loop: Loop) -> None:
    if isinstance(instr, Repeat):
        for inner in instr.body:
            _apply_loop(inner, loop)
    elif isinstance(instr, Stitch | Macro | Each) and instr.loop is Loop.BOTH:
        instr.loop = loop


def parse(text: str, dialect: str = "de") -> ParseResult:
    d = load_dialect(dialect)
    parser = _parser(dialect)
    label_re = re.compile(r"^\s*" + word_regex(d.words["LABEL"]) + r"\s*\d", re.IGNORECASE)
    ignored_re = re.compile(r"^\s*" + word_regex(d.words["IGNORED"]), re.IGNORECASE)

    part = Part()
    diags: list[Diagnostic] = []
    offset = 0
    last_number = 0
    last_kind: str | None = None
    for lineno, raw in enumerate(text.splitlines(keepends=True), start=1):
        line = raw.rstrip("\r\n")
        ctx = _LineCtx(offset, lineno)
        offset += len(raw)
        if not line.strip():
            continue
        try:
            tree = parser.parse(line)
            label, body, count = _ToIR(d, ctx).transform(tree)
        except LarkError as exc:
            col = getattr(exc, "column", None)
            col = col if isinstance(col, int) and col > 0 else 1
            span = ctx.span(col - 1, len(line))
            if label_re.match(line):
                diags.append(Diagnostic("E_SYNTAX", "error", span, {"text": line.strip()}))
            elif ignored_re.match(line):
                diags.append(Diagnostic("I_IGNORED", "info", ctx.span(0, len(line))))
            else:
                diags.append(Diagnostic("W_PROSE", "warning", ctx.span(0, len(line))))
            continue

        line_span = ctx.span(0, len(line))
        into_ring = any(isinstance(i, Stitch) and i.into_ring for i in _walk(body))
        if label is not None:
            kind, first, last = label.kind, label.first, label.last
            if label.loop is not None:
                for instr in body:
                    _apply_loop(instr, label.loop)
        else:
            kind = last_kind or ("round" if into_ring else "row")
            first = last = last_number + 1
        if any(isinstance(i, Stitch) and i.type == "ring" for i in body):
            body = [i for i in body if not (isinstance(i, Stitch) and i.type == "ring")]
            for i in _walk(body):
                if isinstance(i, Stitch):
                    i.into_ring = True
        for number in range(first, last + 1):
            instrs = body if number == first else copy.deepcopy(body)
            part.rows.append(Row(number, kind, instrs, count, line_span))
        last_number, last_kind = last, kind

    return ParseResult(Pattern(dialect=d.id, parts=[part]), diags)


def _walk(instrs: list[Instruction]):
    for i in instrs:
        yield i
        if isinstance(i, Repeat):
            yield from _walk(i.body)


__all__ = ["ParseResult", "parse"]

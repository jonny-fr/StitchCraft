"""Pattern text -> canonical IR.

One structural grammar for all dialects; the vocabulary terminals are filled in
from the dialect tables. Each line is parsed on its own so that a bad line does
not hide the rest of the pattern.
"""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass, field, replace
from functools import cache

from lark import Lark, Token, Transformer, v_args
from lark.exceptions import LarkError

from stitchcraft_core import colors
from stitchcraft_core.expand import MAX_STITCHES
from stitchcraft_core.ir import (
    ColorChange,
    Diagnostic,
    Each,
    Instruction,
    Into,
    Loop,
    Macro,
    Part,
    Pattern,
    Repeat,
    Row,
    Skip,
    SourceSpan,
    Stitch,
    Turn,
)
from stitchcraft_core.notation.detect import detect_dialect
from stitchcraft_core.notation.dialect import (
    CATEGORIES,
    TERMINALS,
    Dialect,
    load_dialect,
    normalise,
    word_regex,
)

GRAMMAR = r"""
start: label? body count? "."?

label: LABEL range lmod* ":"
     | INT "." LABEL lmod* ":"
lmod: "(" LOOPMOD ")"
    | "(" COLOR ")"                 -> lcolor
range: INT ("-" INT)?

body: element ("," element)* ","?
element: LOOPMOD? item times?       -> element
       | INT X LOOPMOD? item        -> prefix_repeat
       | RING                       -> ring_only

?item: stitch | macro | each | turn | group | colorchange | seq | into | skip | tog
stitch: INT? STITCH INT? LOOPMOD? RING?
macro: INT? MACRO LOOPMOD?
into: INT? STITCH LOOPMOD? SAME     -> into_stitch
    | group SAME                   -> into_group
skip: SKIP INT? STW? | INT STW? SKIP
tog: INT? STITCH TOGETHER LOOPMOD? | STITCH TOGN LOOPMOD?
each: INT? STITCH EACH | EACH INT? STITCH
turn: TURN
seq: INT? SEQ
colorchange: CHANGE COLOR
group: "(" body ")" | "[" body "]" | "*" body "*"
times: X INT | INT X
count: "(" INT ")"

INT: /\d+/
TOGN: /\d+\s*tog(?!\w)/i
X: /[x×]/i
%import common.WS
%ignore WS
"""


@dataclass
class ParseResult:
    pattern: Pattern
    diagnostics: list[Diagnostic] = field(default_factory=list)


NEVER = "(?!x)x"  # never matches; terminal regex for an empty word list


@cache
def _dialect(
    dialect_id: str,
    aliases: tuple[tuple[str, str, str], ...] = (),
    seqs: tuple[str, ...] = (),
) -> Dialect:
    """The dialect with glossary synonyms added and sequence abbreviations taken out of
    the vocabulary (so a redefined "zun" means the glossary's instructions)."""
    d = load_dialect(dialect_id)
    if not aliases and not seqs:
        return d
    d = d.with_aliases(aliases)
    gone = {normalise(w) for w in seqs}
    words = {
        k: [w for w in v if k not in TERMINALS.values() or normalise(w) not in gone]
        for k, v in d.words.items()
    }
    return replace(d, words=words)


@cache
def _parser(
    dialect_id: str,
    aliases: tuple[tuple[str, str, str], ...] = (),
    seqs: tuple[str, ...] = (),
) -> Lark:
    d = _dialect(dialect_id, aliases, seqs)
    words = {**d.words, "SEQ": list(seqs)}

    def rx(name: str) -> str:
        # a digit may touch labels ("R1") and stitches ("ch11", "sc2tog")
        glued = name in ("LABEL", "STITCH")
        return word_regex(words[name], digit_follows=glued) if words[name] else NEVER

    terminals = "\n".join(
        f"{name}: /{rx(name)}/i"
        for name in (
            "STITCH",
            "MACRO",
            "LOOPMOD",
            "RING",
            "TURN",
            "EACH",
            "LABEL",
            "CHANGE",
            "SEQ",
            "SAME",
            "SKIP",
            "STW",
            "TOGETHER",
        )
    )
    # codes are case-sensitive (so "B" is a colour but "b" is not), names and hex are not
    names = word_regex(list(colors.names()))
    terminals += f"\nCOLOR: /#[0-9a-fA-F]{{6}}(?!\\w)|(?i:{names})|{colors.CODE}(?!\\w)/"
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
    color: ColorChange | None


@v_args(meta=True)
class _ToIR(Transformer):
    def __init__(
        self,
        dialect: Dialect,
        ctx: _LineCtx,
        refs: list[ColorChange],
        seqs: dict[str, list[Instruction]] | None = None,
    ):
        super().__init__()
        self.d = dialect
        self.ctx = ctx
        self.refs = refs  # every colour change, for the palette check after parsing
        self.seqs = seqs or {}  # glossary abbreviations that stand for several instructions

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
        # "Rd. 1-3 (nur hMg):" or "1. Rd:"
        tok = next(c for c in children if isinstance(c, Token) and c.type == "LABEL")
        num = next((c for c in children if isinstance(c, Token) and c.type == "INT"), None)
        first, last = (
            (int(num), int(num)) if num else next(c for c in children if isinstance(c, tuple))
        )
        loop = next((c for c in children if isinstance(c, Loop)), None)
        color = next((c for c in children if isinstance(c, ColorChange)), None)
        return _Label(self.d.lookup[normalise(tok)][1], first, last, loop, color)

    def lmod(self, meta, children):
        return self._loop(children[0])

    def lcolor(self, meta, children):
        return self._color(children[0], meta)

    def colorchange(self, meta, children):
        return self._color(children[1], meta)

    def _color(self, tok: Token, meta) -> ColorChange:
        change = ColorChange(colors.ref(str(tok)), self._span(meta))
        self.refs.append(change)
        return change

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
        kind = self.d.canonical(toks["MACRO"])
        m = Macro(
            kind="dec" if kind == "invdec" else kind,
            count=int(ints[0]) if ints else 1,
            span=self._span(meta),
        )
        if kind == "invdec":  # worked through the front loops only
            m.loop = Loop.FLO
        if "LOOPMOD" in toks:
            m.loop = self._loop(toks["LOOPMOD"])
        return m

    def into_stitch(self, meta, children):
        ints, toks = self._split(children)
        st = Stitch(
            type=self.d.canonical(toks["STITCH"]),
            count=int(ints[0]) if ints else 1,
            span=self._span(meta),
        )
        if "LOOPMOD" in toks:
            st.loop = self._loop(toks["LOOPMOD"])
        return Into(body=[st], span=st.span)

    def into_group(self, meta, children):
        return Into(body=children[0].body, span=self._span(meta))

    def skip(self, meta, children):
        ints, _ = self._split(children)
        return Skip(count=int(ints[0]) if ints else 1, span=self._span(meta))

    def tog(self, meta, children):
        ints, toks = self._split(children)
        merge = int(re.match(r"\d+", toks["TOGN"]).group()) if "TOGN" in toks else None
        m = Macro(
            kind="dec",
            stitch=self.d.canonical(toks["STITCH"]),
            merge=merge or (int(ints[0]) if ints else 2),
            span=self._span(meta),
        )
        if "LOOPMOD" in toks:
            m.loop = self._loop(toks["LOOPMOD"])
        return m

    def each(self, meta, children):
        ints, toks = self._split(children)
        return Each(
            type=self.d.canonical(toks["STITCH"]),
            count=int(ints[0]) if ints else 1,
            span=self._span(meta),
        )

    def turn(self, meta, children):
        return Turn(span=self._span(meta))

    def seq(self, meta, children):
        ints, toks = self._split(children)
        span = self._span(meta)
        body = copy.deepcopy(self.seqs[normalise(toks["SEQ"])])
        for instr in _walk(body):
            instr.span = span
        return Repeat(body=body, times=int(ints[0]) if ints else 1, span=span)

    def group(self, meta, children):
        return Repeat(body=children[0], times=1, span=self._span(meta))

    def times(self, meta, children):
        return int(next(c for c in children if c.type == "INT"))

    def count(self, meta, children):
        return int(children[0])


def _apply_loop(instr: Instruction, loop: Loop) -> None:
    if isinstance(instr, Repeat | Into):
        for inner in instr.body:
            _apply_loop(inner, loop)
    elif isinstance(instr, Stitch | Macro | Each) and instr.loop is Loop.BOTH:
        instr.loop = loop


def _label_re(d: Dialect) -> re.Pattern[str]:
    return re.compile(
        r"^\s*(?:"
        + word_regex(d.words["LABEL"], digit_follows=True)
        + r"\s*\d|\d+\.\s*"
        + word_regex(d.words["LABEL"])
        + ")",
        re.IGNORECASE,
    )


_SEP = r"\s*(?:=|:|–|—|\s-\s)\s*"
_ENTRY = re.compile(r"^\s*(?P<abbr>[^\s=:–—][^=:–—]{0,29}?)" + _SEP + r"(?P<meaning>\S.*?)\s*$")
_SPLIT = re.compile(r"[,;]\s*(?=[^,;=:–—]{1,30}" + _SEP + ")")


@dataclass
class _Glossary:
    lines: set[int] = field(default_factory=set)
    aliases: list[tuple[str, str, str]] = field(default_factory=list)
    seqs: dict[str, list[Instruction]] = field(default_factory=dict)
    seq_words: list[str] = field(default_factory=list)
    diagnostics: list[Diagnostic] = field(default_factory=list)


def _glossary(lines: list[str], d: Dialect) -> _Glossary:
    """'Abkürzungen: fe = feste Masche, ...' (and the entry lines below it) -> local vocabulary.

    A meaning that is one known term becomes a synonym; one that parses as instructions
    ("1 fM, zun") becomes an abbreviation expanded wherever it is used."""
    out = _Glossary()
    if not d.words["GLOSSARY"]:
        return out
    header = re.compile(r"^\s*" + word_regex(d.words["GLOSSARY"]) + r"\s*:(.*)$", re.IGNORECASE)
    label_re = _label_re(d)
    entries: list[tuple[str, str, SourceSpan]] = []
    offset = 0
    in_block = False
    for lineno, raw in enumerate(lines, start=1):
        line = raw.rstrip("\r\n")
        ctx = _LineCtx(offset, lineno)
        offset += len(raw)
        if m := header.match(line):
            in_block = True
            out.lines.add(lineno)
            rest = m.group(1)
        elif in_block and line.strip() and not label_re.match(line) and _ENTRY.match(line):
            out.lines.add(lineno)
            rest = line
        else:
            in_block = False
            continue
        for chunk in filter(str.strip, _SPLIT.split(rest)):
            if e := _ENTRY.match(chunk):
                entries.append((e["abbr"].strip(), e["meaning"], ctx.span(0, len(line))))

    base = _parser(d.id)
    for abbr, meaning, span in entries:
        term = normalise(re.sub(r"\([^)]*\)", "", meaning).strip(" .,;"))
        if term in d.lookup and d.lookup[term][0] in CATEGORIES:
            out.aliases.append((abbr, *d.lookup[term]))
            continue
        try:
            label, body, count = _ToIR(d, _LineCtx(0, 0), []).transform(base.parse(meaning))
        except LarkError:
            label = body = None
        if label is None and body and not any(isinstance(i, Turn) for i in _walk(body)):
            out.seqs[normalise(abbr)] = body
            out.seq_words.append(abbr)
        else:
            params: dict[str, object] = {"abbr": abbr, "meaning": meaning}
            out.diagnostics.append(Diagnostic("W_GLOSSARY_UNKNOWN", "warning", span, params))
    return out


def parse(text: str, dialect: str = "de") -> ParseResult:
    diags: list[Diagnostic] = []
    if dialect == "auto":
        detected = detect_dialect(text)
        dialect = detected.dialect
        if detected.ambiguous:
            params: dict[str, object] = {"chosen": dialect, "candidates": detected.candidates}
            diags.append(Diagnostic("W_AMBIGUOUS_DIALECT", "warning", None, params))
    lines = text.splitlines(keepends=True)
    glossary = _glossary(lines, load_dialect(dialect))
    diags += glossary.diagnostics
    aliases = tuple(glossary.aliases)
    seq_words = tuple(glossary.seq_words)
    d = _dialect(dialect, aliases, seq_words)
    parser = _parser(dialect, aliases, seq_words)
    label_re = _label_re(d)
    ignored_re = re.compile(r"^\s*" + word_regex(d.words["IGNORED"]), re.IGNORECASE)
    palette_re = re.compile(r"^\s*" + word_regex(d.words["PALETTE"]) + r"\s*:(.*)$", re.IGNORECASE)

    part = Part()
    offset = 0
    last_number = 0
    last_kind: str | None = None
    palette: dict[str, str | None] = {}
    refs: list[ColorChange] = []
    pending: list[Instruction] = []  # colour change on a line of its own, for the next row
    for lineno, raw in enumerate(lines, start=1):
        line = raw.rstrip("\r\n")
        ctx = _LineCtx(offset, lineno)
        offset += len(raw)
        if not line.strip() or lineno in glossary.lines:
            continue
        if m := palette_re.match(line):
            diags += _palette(m.group(1), palette, ctx.span(0, len(line)))
            continue
        try:
            tree = parser.parse(line)
            label, body, count = _ToIR(d, ctx, refs, glossary.seqs).transform(tree)
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
        if label is None and all(isinstance(i, ColorChange) for i in body):
            pending = body
            continue
        if label is not None and label.color is not None:
            body = [label.color, *body]
        body, pending = pending + body, []
        into_ring = any(isinstance(i, Stitch) and i.into_ring for i in _walk(body))
        if label is not None:
            kind, first, last = label.kind, label.first, label.last
            if kind == "short":
                kind = last_kind or ("round" if into_ring else "row")
            if label.loop is not None:
                for instr in body:
                    _apply_loop(instr, label.loop)
        else:
            kind = last_kind or ("round" if into_ring else "row")
            first = last = last_number + 1
        if last - first >= MAX_STITCHES:
            diags.append(Diagnostic("E_TOO_LARGE", "error", line_span, {"limit": MAX_STITCHES}))
            continue
        if any(isinstance(i, Stitch) and i.type == "ring" for i in body):
            body = [i for i in body if not (isinstance(i, Stitch) and i.type == "ring")]
            for i in _walk(body):
                if isinstance(i, Stitch):
                    i.into_ring = True
        for number in range(first, last + 1):
            instrs = body if number == first else copy.deepcopy(body)
            part.rows.append(Row(number, kind, instrs, count, line_span))
        last_number, last_kind = last, kind

    if palette:
        diags += [
            Diagnostic("W_UNKNOWN_COLOR", "warning", c.span, {"name": c.color})
            for c in refs
            if c.color not in palette and colors.known_hex(c.color) is None
        ]
    return ParseResult(Pattern(dialect=d.id, parts=[part], palette=palette), diags)


def _palette(entries: str, palette: dict[str, str | None], span: SourceSpan) -> list[Diagnostic]:
    """'A = creme, B = #c0392b' -> palette entries; unknown colour words are warned."""
    diags = []
    for entry in filter(str.strip, entries.split(",")):
        code, _, value = entry.replace(":", "=").partition("=")
        code, value = code.strip(), value.strip()
        hex_ = colors.known_hex(value) if value else None
        palette[code] = hex_
        if hex_ is None:
            diags.append(Diagnostic("W_UNKNOWN_COLOR", "warning", span, {"name": value or code}))
    return diags


def _walk(instrs: list[Instruction]):
    for i in instrs:
        yield i
        if isinstance(i, Repeat | Into):
            yield from _walk(i.body)


__all__ = ["ParseResult", "parse"]

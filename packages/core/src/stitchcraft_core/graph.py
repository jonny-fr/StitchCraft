"""Stitch graph: the linker assigns every stitch its parent stitch(es) in the previous row.

Node ids follow yarn order, so ``range(len(nodes))`` is the path of the yarn. A magic
ring, if present, is node 0 and is not part of the yarn order of stitches.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from stitchcraft_core.expand import (
    MAX_STITCHES,
    ColorOp,
    EachOp,
    Op,
    SkipOp,
    TurnOp,
    expand_row,
    pattern_size,
)
from stitchcraft_core.ir import Diagnostic, Pattern, SourceSpan


@dataclass
class Node:
    id: int
    row: int  # index into StitchGraph.rows
    type: str
    parents: list[int] = field(default_factory=list)
    counting: bool = True
    turning: bool = False
    op: str | None = None  # "inc" / "dec" macro the stitch came from
    loop: str = "both"
    span: SourceSpan | None = None
    color: str = "A"  # colour reference, see stitchcraft_core.colors


@dataclass
class RowInfo:
    number: int
    kind: str
    node_ids: list[int]
    expected: int | None
    side: int  # +1: the worker faced the front side while working this row
    turned_after: bool
    foundation: bool
    span: SourceSpan | None


@dataclass
class StitchGraph:
    nodes: list[Node]
    rows: list[RowInfo]
    ring: int | None
    diagnostics: list[Diagnostic]

    def counting_ids(self, row: RowInfo) -> list[int]:
        return [n for n in row.node_ids if self.nodes[n].counting]

    def row_neighbors(self) -> list[tuple[int, int]]:
        """Pairs of physically adjacent stitches along a row (or along the spiral)."""
        pairs = []
        prev: int | None = None
        prev_row: RowInfo | None = None
        for row in self.rows:
            ids = [n for n in row.node_ids if not self.nodes[n].turning]
            continues = (
                prev is not None
                and prev_row is not None
                and row.kind == "round"
                and prev_row.kind == "round"
                and not prev_row.turned_after
            )
            if not continues:
                prev = None
            for n in ids:
                if prev is not None:
                    pairs.append((prev, n))
                prev = n
            prev_row = row
        return pairs


def _add_node(
    nodes: list[Node],
    row: int,
    op_type: str,
    parents: list[int],
    op: Op | EachOp,
    *,
    counting: bool = True,
    turning: bool = False,
    macro: str | None = None,
    color: str = "A",
) -> int:
    node = Node(
        id=len(nodes),
        row=row,
        type=op_type,
        parents=parents,
        counting=counting,
        turning=turning,
        op=macro,
        loop=str(op.loop),
        span=op.span,
        color=color,
    )
    nodes.append(node)
    return node.id


def build_graph(pattern: Pattern) -> StitchGraph:
    nodes: list[Node] = []
    rows: list[RowInfo] = []
    diags: list[Diagnostic] = []
    ring: int | None = None
    part = pattern.parts[0] if pattern.parts else None

    if part is None or not part.rows:
        return StitchGraph([], [], None, [Diagnostic("E_EMPTY_PATTERN", "error")])
    if pattern_size(part.rows) > MAX_STITCHES:
        too_large = Diagnostic("E_TOO_LARGE", "error", params={"limit": MAX_STITCHES})
        return StitchGraph([], [], None, [too_large])

    color = next(iter(pattern.palette), "A")
    if any(isinstance(op, Op) and op.ring for op in expand_row(part.rows[0])):
        nodes.append(Node(0, -1, "ring", counting=False, color=color))
        ring = 0

    prev: RowInfo | None = None
    for ri, row in enumerate(part.rows):
        ops = expand_row(row)
        stitch_ops = [o for o in ops if isinstance(o, Op | EachOp)]
        foundation = bool(stitch_ops) and all(
            isinstance(o, Op) and o.type == "ch" for o in stitch_ops
        )
        turned_after = any(isinstance(o, TurnOp) for o in ops) or row.kind == "row"

        available: list[int] = []
        side = 1
        if prev is not None:
            available = [n for n in prev.node_ids if nodes[n].counting]
            if prev.turned_after:
                available.reverse()
                side = prev.side if prev.foundation else -prev.side
            else:
                side = prev.side
            needed = sum(o.consume for o in ops if isinstance(o, Op))
            needed += sum(o.count for o in ops if isinstance(o, SkipOp))
            has_each = any(isinstance(o, EachOp) for o in ops)
            if prev.foundation and (has_each or needed == len(available) - 1):
                nodes[available[0]].turning = True  # "into the 2nd chain from the hook"
                available = available[1:]

        ids: list[int] = []
        ptr = 0
        short = False
        last_parent: int | None = None

        def add(op_type, parents, op, **kw):
            ids.append(_add_node(nodes, ri, op_type, parents, op, color=color, **kw))  # noqa: B023

        for op in ops:
            if isinstance(op, TurnOp):
                continue
            if isinstance(op, ColorOp):
                color = op.color
                continue
            if isinstance(op, SkipOp):
                ptr += op.count
                if ptr > len(available):
                    short = True
                continue
            if isinstance(op, EachOp):
                macro = "inc" if op.count > 1 else None
                while ptr < len(available):
                    last_parent = available[ptr]
                    for _ in range(op.count):
                        add(op.type, [last_parent], op, macro=macro)
                    ptr += 1
                continue
            if op.ring:
                add(op.type, [ring] if ring is not None else [], op)
                continue
            if op.share:
                add(op.type, [last_parent] if last_parent is not None else [], op, macro=op.macro)
                continue
            if op.consume == 0:
                add(op.type, [], op, counting=op.counting, turning=op.turning, macro=op.macro)
                continue
            parents = available[ptr : ptr + op.consume]
            ptr += op.consume
            if len(parents) < op.consume:
                short = True
            if parents:
                last_parent = parents[-1]
            elif last_parent is not None:
                parents = [last_parent]
            add(op.type, parents, op, macro=op.macro)

        info = RowInfo(
            number=row.number,
            kind=row.kind,
            node_ids=ids,
            expected=row.expected_count,
            side=side,
            turned_after=turned_after,
            foundation=foundation,
            span=row.span,
        )
        rows.append(info)

        if prev is not None and not foundation:
            if short:
                diags.append(
                    Diagnostic(
                        "E_TOO_FEW_PARENTS",
                        "error",
                        row.span,
                        {"row": row.number, "needed": ptr, "available": len(available)},
                    )
                )
            elif ptr < len(available):
                diags.append(
                    Diagnostic(
                        "W_UNWORKED",
                        "warning",
                        row.span,
                        {"row": row.number, "left": len(available) - ptr},
                    )
                )
        actual = sum(nodes[n].counting for n in ids)
        if row.expected_count is not None and actual != row.expected_count:
            diags.append(
                Diagnostic(
                    "E_COUNT_MISMATCH",
                    "error",
                    row.span,
                    {"row": row.number, "expected": row.expected_count, "actual": actual},
                )
            )
        prev = info

    return StitchGraph(nodes, rows, ring, diags)

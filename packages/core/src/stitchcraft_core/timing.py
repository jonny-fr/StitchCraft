"""Crochet time estimate: a sum over the stitch graph with the values of data/timing.toml.

No simulation: every stitch the graph holds is one made stitch (turning chains included), plus a
surcharge per macro stitch, per round/row, per colour change and once for the magic ring.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, get_args

from stitchcraft_core.data import load_toml
from stitchcraft_core.graph import StitchGraph
from stitchcraft_core.params import Params

Pace = Literal["anfaenger", "geuebt", "schnell"]
PACES: tuple[str, ...] = get_args(Pace)


@dataclass
class RowTime:
    number: int
    kind: str
    seconds: float  # point estimate, the middle of the range


@dataclass
class TimeEstimate:
    seconds_low: int
    seconds_high: int
    per_row: list[RowTime]


def table() -> dict:
    return load_toml("timing.toml")


def factor(params: Params, pace: str, stitches_per_minute: float | None) -> float:
    """Multiplier on the table: the pace and the yarn, or a measured pace that holds both."""
    t = table()
    if stitches_per_minute is not None:
        if not stitches_per_minute > 0:
            raise ValueError(f"stitches_per_minute must be > 0, got {stitches_per_minute!r}")
        # measured in sc per minute; the other stitches keep their ratio to sc
        return 60.0 / stitches_per_minute / t["stitch"]["sc"]
    if pace not in t["pace"]:
        raise ValueError(f"unknown pace {pace!r}; use one of {', '.join(t['pace'])}")
    y = t["yarn"]
    thickness = 1.0 + y["per_mm"] * (params.yarn_mm - y["reference_mm"])
    yarn = min(max(thickness, y["min"]), y["max"])
    return t["pace"][pace] * yarn * t["material"][params.material]


def estimate(
    graph: StitchGraph,
    params: Params | None = None,
    pace: str = "geuebt",
    stitches_per_minute: float | None = None,
) -> TimeEstimate | None:
    """None when there is nothing to crochet (empty pattern, or too large to build)."""
    f = factor(params or Params(), pace, stitches_per_minute)
    if not graph.rows:
        return None
    t = table()
    stitch, macro, extra = t["stitch"], t["macro"], t["extra"]
    nodes = graph.nodes
    color: str | None = None
    per_row = []
    for ri, row in enumerate(graph.rows):
        seconds = extra["row"]
        if ri == 0 and graph.ring is not None:
            seconds += extra["ring"]
        for n in row.node_ids:
            node = nodes[n]
            seconds += stitch.get(node.type, stitch["sc"])
            if node.op == "inc":
                seconds += macro["inc"]
            elif node.op == "dec":
                # through the front loops only: the invisible decrease
                kind = "invdec" if node.loop == "flo" else "dec"
                seconds += macro[kind] * max(len(node.parents) - 1, 1)
            if color is not None and node.color != color:
                seconds += extra["color_change"]
            color = node.color
        per_row.append(RowTime(row.number, row.kind, seconds * f))
    total = sum(r.seconds for r in per_row)
    spread = t["spread"]
    return TimeEstimate(round(total * (1 - spread)), round(total * (1 + spread)), per_row)

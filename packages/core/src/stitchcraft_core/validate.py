"""Parse + link + count check + time estimate. Diagnostics carry codes and params, never text."""

from __future__ import annotations

from dataclasses import dataclass

from stitchcraft_core.graph import StitchGraph, build_graph
from stitchcraft_core.ir import Diagnostic, Pattern
from stitchcraft_core.notation import parse
from stitchcraft_core.params import Params
from stitchcraft_core.timing import TimeEstimate, estimate


@dataclass
class ValidationResult:
    dialect: str
    pattern: Pattern
    graph: StitchGraph
    diagnostics: list[Diagnostic]
    rows: list[dict[str, object]]
    time_estimate: TimeEstimate | None = None

    @property
    def ok(self) -> bool:
        return not any(d.severity == "error" for d in self.diagnostics)

    @property
    def total_stitches(self) -> int:
        return sum(n.counting for n in self.graph.nodes)


def validate(
    text: str,
    dialect: str = "de",
    params: Params | None = None,
    pace: str = "geuebt",
    stitches_per_minute: float | None = None,
) -> ValidationResult:
    """`params` (yarn thickness, material), `pace` and `stitches_per_minute` only shape the time
    estimate; see stitchcraft_core.timing."""
    parsed = parse(text, dialect=dialect)
    graph = build_graph(parsed.pattern)
    diags = sorted(
        parsed.diagnostics + graph.diagnostics,
        key=lambda d: (d.span is None, d.span.start if d.span else 0),
    )
    rows: list[dict[str, object]] = [
        {
            "number": r.number,
            "kind": r.kind,
            "actual": len(graph.counting_ids(r)),
            "expected": r.expected,
            "line": r.span.line if r.span else None,
        }
        for r in graph.rows
    ]
    time = estimate(graph, params, pace, stitches_per_minute)
    return ValidationResult(parsed.pattern.dialect, parsed.pattern, graph, diags, rows, time)

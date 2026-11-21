"""Parse + link + count check. Diagnostics carry codes and params only, never text."""

from __future__ import annotations

from dataclasses import dataclass

from stitchcraft_core.graph import StitchGraph, build_graph
from stitchcraft_core.ir import Diagnostic, Pattern
from stitchcraft_core.notation import parse


@dataclass
class ValidationResult:
    dialect: str
    pattern: Pattern
    graph: StitchGraph
    diagnostics: list[Diagnostic]
    rows: list[dict[str, object]]

    @property
    def ok(self) -> bool:
        return not any(d.severity == "error" for d in self.diagnostics)

    @property
    def total_stitches(self) -> int:
        return sum(n.counting for n in self.graph.nodes)


def validate(text: str, dialect: str = "de") -> ValidationResult:
    parsed = parse(text, dialect=dialect)
    graph = build_graph(parsed.pattern)
    diags = sorted(
        parsed.diagnostics + graph.diagnostics,
        key=lambda d: d.span.start if d.span else -1,
    )
    rows = [
        {
            "number": r.number,
            "kind": r.kind,
            "actual": len(graph.counting_ids(r)),
            "expected": r.expected,
        }
        for r in graph.rows
    ]
    return ValidationResult(parsed.pattern.dialect, parsed.pattern, graph, diags, rows)

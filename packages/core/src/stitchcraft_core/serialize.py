"""JSON-ready views of core results (shared by CLI, API and MCP)."""

from __future__ import annotations

from stitchcraft_core.ir import Diagnostic
from stitchcraft_core.validate import ValidationResult


def diagnostic_dict(d: Diagnostic) -> dict:
    span = None
    if d.span is not None:
        span = {"start": d.span.start, "end": d.span.end, "line": d.span.line, "col": d.span.col}
    return {"code": d.code, "severity": d.severity, "span": span, "params": d.params}


def validation_dict(v: ValidationResult) -> dict:
    return {
        "dialect": v.dialect,
        "ok": v.ok,
        "total_stitches": v.total_stitches,
        "diagnostics": [diagnostic_dict(d) for d in v.diagnostics],
        "rows": v.rows,
    }

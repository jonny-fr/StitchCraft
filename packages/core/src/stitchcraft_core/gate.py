"""M1 Go/No-Go measurements (plan section 9) and the evaluation report."""

from __future__ import annotations

import time
from datetime import date
from pathlib import Path

import numpy as np

from stitchcraft_core.evaluation import evaluate_reference, frame, main_dimensions
from stitchcraft_core.params import Params
from stitchcraft_core.pipeline import Preview, preview
from stitchcraft_core.yarn import penetration_stats

PIECES = ["1-square", "2-disc", "3-sphere", "4-cup", "5-hyperbolic"]


def _status(ok: bool | None) -> str:
    return "pending" if ok is None else ("pass" if ok else "fail")


def _load(reference: Path) -> dict[str, Preview]:
    out = {}
    for piece in PIECES:
        text = (reference / piece / "pattern.txt").read_text(encoding="utf-8")
        out[piece] = preview(text, "de", Params())
    return out


def _a7(previews: dict[str, Preview]) -> dict[str, float]:
    sphere = previews["3-sphere"]
    dims = main_dimensions(sphere, "stuffed")
    cup = previews["4-cup"]
    g, x = cup.validation.graph, cup.shape.positions
    f = frame(cup)
    stats = {}
    for row in g.rows:
        rel = x[g.counting_ids(row)] - f.origin
        h = rel @ f.up
        stats[row.number] = (h.mean(), np.linalg.norm(rel - np.outer(h, f.up), axis=1).mean())
    angle = float(np.degrees(np.arctan2(stats[16][0] - stats[6][0], stats[16][1] - stats[6][1])))
    hyp = previews["5-hyperbolic"]
    outer = hyp.shape.positions[hyp.validation.graph.counting_ids(hyp.validation.graph.rows[-1])]
    centred = outer - outer.mean(axis=0)
    normal = np.linalg.svd(centred, full_matrices=False)[2][2]
    ruffle = float((centred @ normal).std())
    a = g.counting_ids(g.rows[9])[-1]
    b = g.counting_ids(g.rows[10])[0]
    jog = float((x[b] - x[a]) @ f.up)
    return {
        "sphere_h_over_w": round(dims["height"] / dims["width"], 3),
        "cup_wall_angle_deg": round(angle, 1),
        "hyperbolic_ruffle_std_mm": round(ruffle, 2),
        "spiral_jog_mm": round(jog, 2),
    }


def measure(reference: Path) -> dict[str, dict]:
    previews = _load(reference)
    m: dict[str, dict] = {}

    refs = [evaluate_reference(reference / p) for p in PIECES[:4]]
    a1 = [r.a1_ok for r in refs if r.a1_ok is not None]
    a2 = [r.a2_ok for r in refs[1:] if r.a2_ok is not None]
    m["A1"] = {
        "status": _status(all(a1) if a1 else None),
        "value": {r.piece: r.dimensions for r in refs if r.dimensions} or "no measurements yet",
    }
    m["A2"] = {
        "status": _status(all(a2) if a2 else None),
        "value": {r.piece: r.ious for r in refs if r.ious} or "no silhouette masks yet",
    }

    count_ok = all(
        len(p.validation.graph.counting_ids(r)) == r.expected
        for p in previews.values()
        for r in p.validation.graph.rows
        if r.expected is not None
    ) and all(p.ok for p in previews.values())
    m["A3"] = {"status": _status(count_ok), "value": "stitch counts and parents match all pieces"}

    gaps = {}
    for name, p in previews.items():
        steps = np.linalg.norm(np.diff(p.yarn.points, axis=0), axis=1)
        b = np.flatnonzero(np.diff(p.yarn.stitch_ids) != 0)
        b = b[(b > 0) & (b < len(steps) - 1)]
        gap = float((steps[b] - np.maximum(steps[b - 1], steps[b + 1])).max())
        gaps[name] = round(gap / p.yarn.yarn_radius, 3)
    m["A4"] = {
        "status": _status(all(v <= 0.05 for v in gaps.values())),
        "value": {"max gap / yarn radius": gaps},
    }

    pen = {}
    for name, p in previews.items():
        s = penetration_stats(p.yarn)
        pen[name] = {
            "max_depth_r": round(s.max_depth / p.yarn.yarn_radius, 2),
            "affected": round(s.affected_fraction, 3),
        }
    m["A5"] = {
        "status": _status(
            all(v["max_depth_r"] <= 0.1 and v["affected"] <= 0.01 for v in pen.values())
        ),
        "value": pen,
    }
    m["A6"] = {"status": "pending", "value": "blind test with >= 5 crocheters (manual)"}

    a7 = _a7(previews)
    a7_ok = (
        0.9 <= a7["sphere_h_over_w"] <= 1.1
        and 75 <= a7["cup_wall_angle_deg"] <= 105
        and a7["hyperbolic_ruffle_std_mm"] > 0
        and a7["spiral_jog_mm"] > 0
    )
    m["A7"] = {"status": _status(a7_ok), "value": a7}

    text = (reference / "4-cup" / "pattern.txt").read_text(encoding="utf-8")
    hashes = {preview(text, "de", Params()).yarn_hash for _ in range(2)}
    m["A8"] = {
        "status": _status(len(hashes) == 1),
        "value": f"{len(hashes)} distinct hash(es) over 2 runs",
    }

    sphere_text = (reference / "3-sphere" / "pattern.txt").read_text(encoding="utf-8")
    t0 = time.perf_counter()
    preview(sphere_text, "de", Params())
    seconds = time.perf_counter() - t0
    m["A9"] = {
        "status": _status(seconds < 5.0),
        "value": f"sphere (432 st) preview {seconds:.2f} s on this machine; viewer FPS: manual",
    }
    return m


def write_report(reference: Path, out: Path) -> str:
    m = measure(reference)
    lines = [
        "# M1-Abnahme: 3D-Spike (Go/No-Go)",
        "",
        f"Stand: {date.today().isoformat()} · erzeugt mit `uv run stitchcraft gate`",
        "",
        "| # | Status | Messwert |",
        "|---|---|---|",
    ]
    for key in sorted(m):
        value = m[key]["value"]
        lines.append(f"| {key} | {m[key]['status']} | `{value}` |")
    pending = [k for k in m if m[k]["status"] == "pending"]
    failed = [k for k in m if m[k]["status"] == "fail"]
    lines += [
        "",
        "## Go/No-Go",
        "",
        f"- offen (Fotos/Blindtest nötig): {', '.join(pending) or '–'}",
        f"- nicht erfüllt: {', '.join(failed) or '–'}",
        "",
        "Entscheidung erst, wenn A1, A2 und A6 gemessen sind (Plan §9).",
        "",
    ]
    text = "\n".join(lines)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return text

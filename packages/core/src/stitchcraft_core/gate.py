"""Acceptance measurements (plan section 9) and the evaluation reports: M1 Go/No-Go and the
M5 gate (the same criteria for pieces in hdc/dc/tr)."""

from __future__ import annotations

import dataclasses
import time
import tomllib
from datetime import date
from pathlib import Path

import numpy as np

from stitchcraft_core.evaluation import evaluate_reference, frame, main_dimensions
from stitchcraft_core.notation import parse
from stitchcraft_core.params import Params
from stitchcraft_core.pipeline import Preview, PreviewError, normalised_ir, preview
from stitchcraft_core.yarn import TALL_STITCHES, penetration_stats

PIECES = ["1-square", "2-disc", "3-sphere", "4-cup", "5-hyperbolic"]


def _status(ok: bool | None) -> str:
    return "pending" if ok is None else ("pass" if ok else "fail")


def _gap(p: Preview) -> float:
    """Largest jump in sample spacing where one stitch hands over to the next (/ radius)."""
    steps = np.linalg.norm(np.diff(p.yarn.points, axis=0), axis=1)
    b = np.flatnonzero(np.diff(p.yarn.stitch_ids) != 0)
    b = b[(b > 0) & (b < len(steps) - 1)]
    gap = float((steps[b] - np.maximum(steps[b - 1], steps[b + 1])).max())
    return round(gap / p.yarn.yarn_radius, 3)


def _penetration(p: Preview) -> dict[str, float]:
    s = penetration_stats(p.yarn)
    return {
        "max_depth_r": round(s.max_depth / p.yarn.yarn_radius, 2),
        "affected": round(s.affected_fraction, 3),
    }


def _a5_ok(v: dict[str, float]) -> bool:
    return v["max_depth_r"] <= 0.1 and v["affected"] <= 0.01


def _counts_ok(previews: dict[str, Preview]) -> bool:
    return all(
        len(p.validation.graph.counting_ids(r)) == r.expected
        for p in previews.values()
        for r in p.validation.graph.rows
        if r.expected is not None
    ) and all(p.ok for p in previews.values())


def _a4(previews: dict[str, Preview]) -> dict:
    gaps = {name: _gap(p) for name, p in previews.items()}
    return {
        "status": _status(all(v <= 0.05 for v in gaps.values())),
        "value": {"max gap / yarn radius": gaps},
    }


def _a5(previews: dict[str, Preview]) -> dict:
    pen = {name: _penetration(p) for name, p in previews.items()}
    return {"status": _status(all(_a5_ok(v) for v in pen.values())), "value": pen}


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

    count_ok = _counts_ok(previews)
    m["A3"] = {"status": _status(count_ok), "value": "stitch counts and parents match all pieces"}

    m["A4"] = _a4(previews)
    m["A5"] = _a5(previews)
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


def write_report(
    reference: Path, out: Path, milestone: str = "m1", corpus: Path | None = None
) -> str:
    if milestone == "m5":
        return _write_m5_report(reference, out, corpus)
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
    ]
    decision = out.parent / "m1-decision.md"  # recorded by hand, survives regeneration
    if decision.exists():
        lines += ["### Entscheidung", "", decision.read_text(encoding="utf-8").strip(), ""]
    else:
        lines += ["Entscheidung erst, wenn A1, A2 und A6 gemessen sind (Plan §9).", ""]
    text = "\n".join(lines)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return text


# --- M5: tall stitches ----------------------------------------------------------------------

M5_PIECE = "6-dc-square"
# small pieces for the other tall stitches (test pieces, not reference pieces): A4 and A5
M5_EXTRA = {
    "hstb-quadrat": "R 1: 11 Lm, wenden\nR 2-8: 2 Lm, 10 hStb, wenden (10)\n",
    "dstb-quadrat": "R 1: 11 Lm, wenden\nR 2-5: 4 Lm, 10 DStb, wenden (10)\n",
    "stb-scheibe": (
        "Rd. 1: 12 Stb in MR (12)\nRd. 2: (2 Stb in 1 M) x12 (24)\n"
        "Rd. 3: (1 Stb, 2 Stb in 1 M) x12 (36)\n"
    ),
    "stb-abnahmen": (
        "R 1: 13 Lm, wenden\nR 2: 3 Lm, 12 Stb, wenden (12)\n"
        "R 3: 3 Lm, 2 Stb zus. abm., 8 Stb, 2 Stb zus. abm., wenden (10)\n"
    ),
}
ROW_PITCH_RATIO = (1.7, 2.3)  # dc / sc row pitch; the library has dc = 2 x sc
FLAT_RMS_MAX = 0.05  # RMS distance to the best-fit plane / width of the piece


def m5_patterns(reference: Path) -> dict[str, str]:
    """Piece 6 in its dialects (from metadata.toml): dialect -> pattern text."""
    folder = reference / M5_PIECE
    meta = tomllib.loads((folder / "metadata.toml").read_text(encoding="utf-8"))
    return {d: (folder / f).read_text(encoding="utf-8") for f, d in meta["dialects"].items()}


def dialect_neutral_ir(text: str, dialect: str) -> str:
    pattern = parse(text, dialect=dialect).pattern
    return normalised_ir(dataclasses.replace(pattern, dialect=""))


def graph_signature(p: Preview) -> tuple:
    g = p.validation.graph
    nodes = tuple((n.type, tuple(n.parents), n.counting, n.turning, n.op, n.loop) for n in g.nodes)
    return nodes, tuple((r.number, len(g.counting_ids(r)), r.expected) for r in g.rows)


def row_pitch(p: Preview) -> float:
    """Mean distance in mm between the centroids of consecutive worked rows."""
    g, x = p.validation.graph, p.shape.positions
    rows = [g.counting_ids(r) for r in g.rows if not r.foundation and g.counting_ids(r)]
    centroids = np.array([x[ids].mean(axis=0) for ids in rows])
    return float(np.linalg.norm(np.diff(centroids, axis=0), axis=1).mean())


def flat_rms(p: Preview) -> float:
    """RMS distance of all stitch positions to their best-fit plane, / width of the piece."""
    g = p.validation.graph
    x = p.shape.positions[[n.id for n in g.nodes if n.counting]]
    centred = x - x.mean(axis=0)
    normal = np.linalg.svd(centred, full_matrices=False)[2][2]
    rms = float(np.sqrt(np.mean((centred @ normal) ** 2)))
    return rms / main_dimensions(p, "flat")["width"]


def measure_m5(reference: Path) -> dict[str, dict]:
    texts = m5_patterns(reference)
    versions = {d: preview(t, d, Params()) for d, t in texts.items()}
    piece = versions["de"]
    extra = {name: preview(t, "de", Params()) for name, t in M5_EXTRA.items()}
    m: dict[str, dict] = {}

    same = (
        len({dialect_neutral_ir(t, d) for d, t in texts.items()}) == 1
        and len({graph_signature(p) for p in versions.values()}) == 1
        and len({p.yarn_hash for p in versions.values()}) == 1
    )
    counts = _counts_ok(versions)
    m["A3"] = {
        "status": _status(counts and same),
        "value": f"stitch counts and parents match: {counts}; de/en-US/en-UK give the same "
        f"IR, graph and yarn hash: {same}",
    }
    m["A4"] = _a4({M5_PIECE: piece, **extra})
    m["A5"] = _a5({M5_PIECE: piece, **extra})

    sc = preview(
        (reference / "1-square" / "pattern.txt").read_text(encoding="utf-8"), "de", Params()
    )
    a7 = {
        "row_pitch_dc_over_sc": round(row_pitch(piece) / row_pitch(sc), 3),
        "flat_rms_over_width": round(flat_rms(piece), 4),
    }
    lo, hi = ROW_PITCH_RATIO
    a7_ok = lo <= a7["row_pitch_dc_over_sc"] <= hi and a7["flat_rms_over_width"] <= FLAT_RMS_MAX
    m["A7"] = {"status": _status(a7_ok), "value": a7}

    hashes = {preview(texts["de"], "de", Params()).yarn_hash for _ in range(2)} | {piece.yarn_hash}
    m["A8"] = {
        "status": _status(len(hashes) == 1),
        "value": f"{len(hashes)} distinct hash(es) over 3 runs",
    }

    seconds = {}
    for name, text in (
        (M5_PIECE, texts["de"]),
        ("3-sphere", (reference / "3-sphere" / "pattern.txt").read_text(encoding="utf-8")),
    ):
        t0 = time.perf_counter()
        preview(text, "de", Params())
        seconds[name] = time.perf_counter() - t0
    m["A9"] = {
        "status": _status(all(s < 5.0 for s in seconds.values())),
        "value": ", ".join(f"{k} {v:.2f} s" for k, v in seconds.items()) + " on this machine",
    }
    return m


def corpus_tall_a5(corpus: Path) -> dict[str, dict[str, float]]:
    """A5 for every corpus pattern with hdc/dc/tr, read in the dialect of its folder."""
    out = {}
    for path in sorted(corpus.glob("*/*.txt")):
        dialect = path.parent.name
        text = path.read_text(encoding="utf-8")
        try:
            p = preview(text, dialect, Params())
        except PreviewError:
            continue
        if any(n.type in TALL_STITCHES for n in p.validation.graph.nodes):
            out[f"{dialect}/{path.stem}"] = _penetration(p)
    return out


def _write_m5_report(reference: Path, out: Path, corpus: Path | None) -> str:
    m = measure_m5(reference)
    lines = [
        "# M5-Abnahme: hStb, Stb und DStb",
        "",
        f"Stand: {date.today().isoformat()} · erzeugt mit `uv run stitchcraft gate --milestone m5`",
        "",
        f"Referenzstück 6 (`tests/reference/{M5_PIECE}`, de/en-US/en-UK) und die Teststücke "
        f"{', '.join(M5_EXTRA)} (nur A4/A5). A7: Reihenabstand Stb/fM in "
        f"{ROW_PITCH_RATIO[0]}–{ROW_PITCH_RATIO[1]}, RMS-Abstand zur Ebene ≤ "
        f"{FLAT_RMS_MAX:.0%} der Breite.",
        "",
        "| # | Status | Messwert |",
        "|---|---|---|",
    ]
    for key in sorted(m):
        lines.append(f"| {key} | {m[key]['status']} | `{m[key]['value']}` |")
    failed = [k for k in m if m[k]["status"] == "fail"]
    lines += ["", f"Nicht erfüllt: {', '.join(failed) or '–'}", ""]
    if corpus is not None:
        lines += [
            "## Korpus: A5 der Anleitungen mit hStb/Stb/DStb (informativ, nicht gegatet)",
            "",
            "| Anleitung | max. Eindringtiefe / Garnradius | betroffene Paare | A5 |",
            "|---|---|---|---|",
        ]
        for name, v in corpus_tall_a5(corpus).items():
            ok = "ok" if _a5_ok(v) else "**über Schwelle**"
            lines.append(f"| {name} | {v['max_depth_r']} | {v['affected']} | {ok} |")
        lines.append("")
    notes = out.parent / f"{out.stem}-notes.md"  # visual inspection, written by hand
    if notes.exists():
        lines += ["## Sichtprüfung", "", notes.read_text(encoding="utf-8").strip(), ""]
    text = "\n".join(lines)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    return text

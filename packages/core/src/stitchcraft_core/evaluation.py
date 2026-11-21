"""Comparison against photographed reference pieces (M1 gate, criteria A1 and A2).

Masks are PNGs (white = piece) in the piece's natural pose: rounds with their axis vertical
(start of the work at the bottom), flat pieces seen from the front with rows horizontal.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from scipy import ndimage

from stitchcraft_core.params import Params
from stitchcraft_core.pipeline import Preview, preview

A1_TOLERANCE = 0.10
A2_MIN_IOU = 0.85


@dataclass
class Frame:
    origin: np.ndarray
    up: np.ndarray  # growth axis (rounds) or across the rows (flat)
    right: np.ndarray
    depth: np.ndarray  # towards the camera for the front view


def frame(p: Preview) -> Frame:
    g = p.validation.graph
    x = p.shape.positions
    pts = p.yarn.points
    origin = pts.mean(axis=0)
    counting_rows = [r for r in g.rows if g.counting_ids(r)]
    if any(r.kind == "round" for r in g.rows):
        start = x[g.counting_ids(counting_rows[0])].mean(axis=0)
        end = x[g.counting_ids(counting_rows[-1])].mean(axis=0)
        up = end - start
        if np.linalg.norm(up) < 1e-6:  # flat disc: use the surface normal
            _, _, vt = np.linalg.svd(pts - origin, full_matrices=False)
            up = vt[2]
        up /= np.linalg.norm(up)
        right = np.cross(up, [0.0, 0.0, 1.0] if abs(up[2]) < 0.9 else [1.0, 0.0, 0.0])
        right /= np.linalg.norm(right)
        return Frame(origin, up, right, np.cross(right, up))
    _, _, vt = np.linalg.svd(pts - origin, full_matrices=False)
    normal = vt[2]
    row = g.counting_ids(counting_rows[min(1, len(counting_rows) - 1)])
    right = x[row[-1]] - x[row[0]]
    right -= (right @ normal) * normal
    right /= np.linalg.norm(right)
    up = np.cross(normal, right)
    return Frame(origin, up, right, normal)


def main_dimensions(p: Preview, form: str) -> dict[str, float]:
    """Main dimensions in mm, including the yarn thickness."""
    f = frame(p)
    rel = p.yarn.points - f.origin
    pad = 2 * p.yarn.yarn_radius
    if form == "flat":
        return {
            "width": float(np.ptp(rel @ f.right)) + pad,
            "height": float(np.ptp(rel @ f.up)) + pad,
        }
    along = rel @ f.up
    radial = rel - np.outer(along, f.up)
    return {
        "width": 2 * float(np.linalg.norm(radial, axis=1).max()) + pad,
        "height": float(np.ptp(along)) + pad,
    }


def silhouette(p: Preview, view: str, mm_per_px: float) -> np.ndarray:
    """Orthographic silhouette as a boolean image (row 0 = top)."""
    f = frame(p)
    rel = p.yarn.points - f.origin
    if view == "front":
        cols, rows = rel @ f.right, rel @ f.up
    elif view == "side":
        cols, rows = rel @ f.depth, rel @ f.up
    elif view == "top":
        cols, rows = rel @ f.right, rel @ f.depth
    else:
        raise ValueError(f"unknown view {view!r}")
    r_px = p.yarn.yarn_radius / mm_per_px
    margin = int(np.ceil(r_px)) + 2
    c = np.round((cols - cols.min()) / mm_per_px).astype(int) + margin
    r = np.round((rows.max() - rows) / mm_per_px).astype(int) + margin
    img = np.zeros((r.max() + margin + 1, c.max() + margin + 1), dtype=bool)
    img[r, c] = True
    radius = int(np.ceil(r_px))
    yy, xx = np.mgrid[-radius : radius + 1, -radius : radius + 1]
    disk = xx**2 + yy**2 <= r_px**2
    img = ndimage.binary_dilation(img, structure=disk)
    return ndimage.binary_fill_holes(img)


def _centred(mask: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    cy, cx = ndimage.center_of_mass(mask)
    out = np.zeros(shape, dtype=bool)
    ys, xs = np.nonzero(mask)
    ys = np.round(ys - cy + shape[0] / 2).astype(int)
    xs = np.round(xs - cx + shape[1] / 2).astype(int)
    keep = (ys >= 0) & (ys < shape[0]) & (xs >= 0) & (xs < shape[1])
    out[ys[keep], xs[keep]] = True
    return out


def iou(a: np.ndarray, b: np.ndarray) -> float:
    """Intersection over union after aligning both masks at their centroids."""
    h = 2 * max(a.shape[0], b.shape[0])
    w = 2 * max(a.shape[1], b.shape[1])
    ca, cb = _centred(a, (h, w)), _centred(b, (h, w))
    union = np.logical_or(ca, cb).sum()
    return float(np.logical_and(ca, cb).sum() / union) if union else 0.0


def load_mask(path: Path) -> np.ndarray:
    from PIL import Image

    return np.asarray(Image.open(path).convert("L")) > 127


@dataclass
class ReferenceResult:
    piece: str
    available: bool
    dimensions: dict[str, dict[str, float]] = field(default_factory=dict)
    ious: dict[str, float] = field(default_factory=dict)

    @property
    def a1_ok(self) -> bool | None:
        if not self.dimensions:
            return None
        return all(abs(d["error"]) <= A1_TOLERANCE for d in self.dimensions.values())

    @property
    def a2_ok(self) -> bool | None:
        if not self.ious:
            return None
        return all(v >= A2_MIN_IOU for v in self.ious.values())


def evaluate_reference(piece_dir: Path) -> ReferenceResult:
    meta = tomllib.loads((piece_dir / "metadata.toml").read_text(encoding="utf-8"))
    measured_path = piece_dir / "measurements.toml"
    result = ReferenceResult(piece_dir.name, measured_path.exists())
    if not result.available:
        return result
    measured = tomllib.loads(measured_path.read_text(encoding="utf-8"))
    params = Params(
        yarn_mm=meta.get("yarn_mm", 2.0),
        hook_mm=meta.get("hook_mm", 3.5),
        gauge_stitches=meta.get("gauge_stitches"),
        gauge_rows=meta.get("gauge_rows"),
        fill=meta.get("fill", 0.7),
    )
    text = (piece_dir / "pattern.txt").read_text(encoding="utf-8")
    p = preview(text, meta.get("dialect", "de"), params)
    sim = main_dimensions(p, meta.get("form", "flat"))
    for name in ("width", "height"):
        if name in measured:
            real = float(measured[name])
            result.dimensions[name] = {
                "real_mm": real,
                "sim_mm": round(sim[name], 1),
                "error": round((sim[name] - real) / real, 3),
            }
    mm_per_px = float(measured.get("mm_per_px", 0.25))
    for view in ("front", "side", "top"):
        mask_path = piece_dir / "masks" / f"{view}.png"
        if mask_path.exists():
            result.ious[view] = round(iou(silhouette(p, view, mm_per_px), load_mask(mask_path)), 3)
    return result

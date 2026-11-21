"""Vectorised XPBD solver (Jacobi within a constraint group, Gauss-Seidel across groups).

The solver only knows particles and constraints; stitch semantics live in sim/__init__.py.
This keeps the interface small enough to port to Rust/WASM later.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.spatial import cKDTree

EPS = 1e-9
OMEGA = 1.5  # over-relaxation for averaged Jacobi corrections


def _scatter(n: int, idx: np.ndarray, vec: np.ndarray) -> np.ndarray:
    out = np.empty((n, 3))
    for axis in range(3):
        out[:, axis] = np.bincount(idx, weights=vec[:, axis], minlength=n)
    return out


@dataclass
class DistanceGroup:
    i: np.ndarray
    j: np.ndarray
    rest: np.ndarray
    compliance: np.ndarray
    unilateral: bool = False  # only push apart (collision)
    compress_compliance: np.ndarray | None = None  # softer when shorter than rest (yarn bunches)
    lam: np.ndarray = field(init=False)

    def __post_init__(self) -> None:
        self.compliance = np.broadcast_to(np.asarray(self.compliance, float), self.rest.shape)
        if self.compress_compliance is not None:
            self.compress_compliance = np.broadcast_to(
                np.asarray(self.compress_compliance, float), self.rest.shape
            )
        self.lam = np.zeros_like(self.rest)

    def project(self, x: np.ndarray, w: np.ndarray, dt: float) -> None:
        if len(self.i) == 0:
            return
        d = x[self.i] - x[self.j]
        length = np.maximum(np.linalg.norm(d, axis=1), EPS)
        c = length - self.rest
        if self.unilateral:
            c = np.minimum(c, 0.0)
        normal = d / length[:, None]
        alpha = self.compliance
        if self.compress_compliance is not None:
            alpha = np.where(c < 0, self.compress_compliance, alpha)
        at = alpha / dt**2
        wi, wj = w[self.i], w[self.j]
        dl = (-c - at * self.lam) / (wi + wj + at + EPS)
        self.lam += dl
        corr = dl[:, None] * normal
        n = len(x)
        acc = _scatter(n, self.i, wi[:, None] * corr) - _scatter(n, self.j, wj[:, None] * corr)
        count = np.bincount(self.i, minlength=n) + np.bincount(self.j, minlength=n)
        x += OMEGA * acc / np.maximum(count, 1)[:, None]


@dataclass
class VolumeConstraint:
    faces: np.ndarray
    target: float
    compliance: float
    lam: float = 0.0

    def volume(self, x: np.ndarray) -> float:
        a, b, c = (x[self.faces[:, k]] for k in range(3))
        return float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0)

    def project(self, x: np.ndarray, w: np.ndarray, dt: float) -> None:
        a, b, c = (x[self.faces[:, k]] for k in range(3))
        n = len(x)
        grad = (
            _scatter(n, self.faces[:, 0], np.cross(b, c))
            + _scatter(n, self.faces[:, 1], np.cross(c, a))
            + _scatter(n, self.faces[:, 2], np.cross(a, b))
        ) / 6.0
        c_val = self.volume(x) - self.target
        at = self.compliance / dt**2
        denom = float((w * np.einsum("ij,ij->i", grad, grad)).sum()) + at
        dl = (-c_val - at * self.lam) / (denom + EPS)
        self.lam += dl
        x += w[:, None] * dl * grad


@dataclass
class Collision:
    """Particle self-collision via spatial queries, excluding near neighbours in the graph."""

    radius: float
    excluded: np.ndarray  # sorted int64 keys i * n + j (i < j)
    compliance: float = 0.0

    def group(self, x: np.ndarray, active: np.ndarray) -> DistanceGroup | None:
        ids = np.flatnonzero(active)
        pairs = cKDTree(x[ids]).query_pairs(self.radius, output_type="ndarray")
        if len(pairs) == 0:
            return None
        pairs = ids[pairs]
        pairs = np.sort(pairs, axis=1)
        keys = pairs[:, 0].astype(np.int64) * len(x) + pairs[:, 1]
        keep = ~np.isin(keys, self.excluded, assume_unique=False)
        pairs = pairs[keep]
        if len(pairs) == 0:
            return None
        order = np.lexsort((pairs[:, 1], pairs[:, 0]))  # deterministic order
        pairs = pairs[order]
        return DistanceGroup(
            pairs[:, 0],
            pairs[:, 1],
            np.full(len(pairs), self.radius),
            np.asarray(self.compliance),
            unilateral=True,
        )


@dataclass
class Solver:
    x: np.ndarray
    groups: list
    volume: VolumeConstraint | None = None
    collision: Collision | None = None
    dt: float = 1.0 / 60.0
    damping: float = 0.9
    iterations: int = 8
    collision_every: int = 2
    w: np.ndarray = field(init=False)
    v: np.ndarray = field(init=False)

    def __post_init__(self) -> None:
        self.w = np.ones(len(self.x))
        self.v = np.zeros_like(self.x)

    def step(self) -> float:
        prev = self.x.copy()
        self.x += self.v * self.dt
        for g in self.groups:
            g.lam[:] = 0.0
        if self.volume is not None:
            self.volume.lam = 0.0
        coll = None
        for it in range(self.iterations):
            if self.collision is not None and it % self.collision_every == 0:
                coll = self.collision.group(self.x, self.w > 0)
            for g in self.groups:
                g.project(self.x, self.w, self.dt)
            if self.volume is not None:
                self.volume.project(self.x, self.w, self.dt)
            if coll is not None:
                coll.project(self.x, self.w, self.dt)
        self.v = (self.x - prev) / self.dt * self.damping
        return float(np.abs(self.x - prev).max())

    def run(self, max_steps: int, tol: float) -> int:
        for s in range(max_steps):
            if self.step() < tol and s > 10:
                return s + 1
        return max_steps


def dihedral_angle_and_grad(x: np.ndarray, quads: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Signed dihedral angles (0 = flat) and their gradients (Bridson et al. 2003).

    quads rows are (i, j, k, l): shared edge i->j, triangles (i, j, k) and (j, i, l).
    Returns theta (E,) and grad (E, 4, 3) ordered like the quad columns.
    """
    x3, x4, x1, x2 = (x[quads[:, c]] for c in range(4))
    e = x4 - x3
    e_len = np.maximum(np.linalg.norm(e, axis=1), EPS)
    e_hat = e / e_len[:, None]
    n1 = np.cross(x1 - x3, x1 - x4)
    n2 = np.cross(x2 - x4, x2 - x3)
    n1_sq = np.maximum(np.einsum("ij,ij->i", n1, n1), EPS)
    n2_sq = np.maximum(np.einsum("ij,ij->i", n2, n2), EPS)
    n1_hat = n1 / np.sqrt(n1_sq)[:, None]
    n2_hat = n2 / np.sqrt(n2_sq)[:, None]
    sin_t = np.einsum("ij,ij->i", np.cross(n1_hat, n2_hat), e_hat)
    cos_t = np.einsum("ij,ij->i", n1_hat, n2_hat)
    theta = np.arctan2(sin_t, cos_t)

    a1 = n1 / n1_sq[:, None]
    a2 = n2 / n2_sq[:, None]
    u1 = e_len[:, None] * a1
    u2 = e_len[:, None] * a2
    d13 = np.einsum("ij,ij->i", x1 - x4, e) / e_len
    d23 = np.einsum("ij,ij->i", x2 - x4, e) / e_len
    d14 = np.einsum("ij,ij->i", x1 - x3, e) / e_len
    d24 = np.einsum("ij,ij->i", x2 - x3, e) / e_len
    u3 = d13[:, None] * a1 + d23[:, None] * a2
    u4 = -d14[:, None] * a1 - d24[:, None] * a2
    # Bridson's gradients are for the opposite sign convention of theta
    grad = -np.stack([u3, u4, u1, u2], axis=1)
    return theta, grad


@dataclass
class DihedralGroup:
    quads: np.ndarray  # (E, 4)
    rest: np.ndarray  # rest angles
    compliance: np.ndarray
    lam: np.ndarray = field(init=False)

    def __post_init__(self) -> None:
        self.compliance = np.broadcast_to(np.asarray(self.compliance, float), self.rest.shape)
        self.lam = np.zeros_like(self.rest)

    def project(self, x: np.ndarray, w: np.ndarray, dt: float) -> None:
        if len(self.quads) == 0:
            return
        theta, grad = dihedral_angle_and_grad(x, self.quads)
        c = np.angle(np.exp(1j * (theta - self.rest)))
        wq = w[self.quads]  # (E, 4)
        denom = (wq * np.einsum("eck,eck->ec", grad, grad)).sum(axis=1)
        at = self.compliance / dt**2
        dl = (-c - at * self.lam) / (denom + at + EPS)
        self.lam += dl
        n = len(x)
        acc = np.zeros((n, 3))
        count = np.zeros(n)
        for col in range(4):
            idx = self.quads[:, col]
            acc += _scatter(n, idx, (wq[:, col] * dl)[:, None] * grad[:, col])
            count += np.bincount(idx, minlength=n)
        x += OMEGA * acc / np.maximum(count, 1)[:, None]

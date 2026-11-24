import type { Yarn } from "./yarn";

/**
 * Level of detail. The yarn is split into chunks of consecutive points; each chunk picks its level from how many
 * device pixels the yarn is thick at its nearest point, so a close-up gets the full tube with fuzz while the rest
 * of a large piece (and the whole piece in the overview) gets a coarse tube. Chunks outside the view are culled.
 */
export interface Level {
  sides: number;
  /** Every `step`-th yarn point (the chunk's last point is always kept). */
  step: number;
  /** Share of the material's fuzz shells drawn (0: none); fewer shells where single fibres are below a pixel. */
  fuzz: number;
  /** Coarser tube the shells are drawn on: the fuzz needs no exact outline, and every shell repeats its vertices. */
  shellSides: number;
  shellStep: number;
  /** Yarn diameter in device pixels from which a chunk switches to this level … */
  enter: number;
  /** … and below which it leaves it again (hysteresis against flicker). */
  leave: number;
}

export const LEVELS: readonly Level[] = [
  { sides: 12, step: 1, fuzz: 1, shellSides: 8, shellStep: 1, enter: 48, leave: 36 }, // close-up: round silhouettes
  { sides: 8, step: 1, fuzz: 0.5, shellSides: 6, shellStep: 2, enter: 10, leave: 7 }, // near
  { sides: 4, step: 2, fuzz: 0, shellSides: 0, shellStep: 0, enter: 0, leave: 0 }, // far
];
export const FAR = LEVELS.length - 1;

/** Fuzz shells a level draws of a material with `shells` shells. */
export const levelShells = (level: number, shells: number) => Math.ceil(shells * LEVELS[level].fuzz);

/** Pieces up to this many yarn points never use the far level: they are cheap at full detail. */
export const LOD_MIN_POINTS = 100_000;

export const CHUNK_POINTS = 2048;

export interface Chunk {
  start: number;
  /** Inclusive: neighbouring chunks share their boundary point, so the tube stays closed. */
  end: number;
  centre: [number, number, number];
  radius: number;
}

/** Splits the yarn into chunks of at most `size` segments, with bounding spheres (yarn radius included). */
export function chunks(yarn: Yarn, size = CHUNK_POINTS): Chunk[] {
  const out: Chunk[] = [];
  const p = yarn.points;
  if (yarn.count === 0) return out;
  for (let start = 0; ; start += size) {
    const end = Math.min(start + size, yarn.count - 1);
    let x0 = Infinity, y0 = Infinity, z0 = Infinity, x1 = -Infinity, y1 = -Infinity, z1 = -Infinity, r = 0;
    for (let i = start; i <= end; i++) {
      x0 = Math.min(x0, p[i * 3]); x1 = Math.max(x1, p[i * 3]);
      y0 = Math.min(y0, p[i * 3 + 1]); y1 = Math.max(y1, p[i * 3 + 1]);
      z0 = Math.min(z0, p[i * 3 + 2]); z1 = Math.max(z1, p[i * 3 + 2]);
      r = Math.max(r, yarn.radius[i]);
    }
    const centre: [number, number, number] = [(x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2];
    out.push({ start, end, centre, radius: Math.hypot(x1 - x0, y1 - y0, z1 - z0) / 2 + r });
    if (end >= yarn.count - 1) break;
  }
  return out;
}

/** Device pixels a yarn of `radius` covers at `distance` with a vertical field of view `fov` (degrees). */
export function yarnPixels(radius: number, distance: number, fov: number, heightPx: number): number {
  const view = 2 * Math.max(distance, 1e-6) * Math.tan((fov * Math.PI) / 360);
  return ((2 * radius) / view) * heightPx;
}

/** Level of a chunk whose yarn is `px` pixels thick; `current` is -1 before the first frame, `coarsest` the last level allowed. */
export function nextLevel(current: number, px: number, coarsest = FAR): number {
  let target = coarsest;
  for (let i = 0; i < coarsest; i++)
    if (px >= LEVELS[i].enter) {
      target = i;
      break;
    }
  // coarser only once the yarn is thinner than the current level's `leave`
  if (current !== -1 && current < target && px >= LEVELS[current].leave) return current;
  return target;
}

/** Number of segments to draw of a chunk built from `points` when the yarn is shown up to point `visible` (exclusive). */
export function visibleSegments(points: ArrayLike<number>, visible: number): number {
  let lo = 0, hi = points.length; // first index with points[i] >= visible
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (points[mid] < visible) lo = mid + 1;
    else hi = mid;
  }
  return Math.max(lo - 1, 0);
}

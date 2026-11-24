import { BufferAttribute, BufferGeometry, Color } from "three";

export interface Yarn {
  count: number;
  points: Float32Array; // xyz per point, mm
  radius: Float32Array;
  stitchIds: Uint32Array;
  segmentOffsets: Uint32Array;
}

/** Decodes the API's yarn.bin (see stitchcraft_core.export.encode_yarn_bin). */
export function decodeYarnBin(buf: ArrayBuffer): Yarn {
  const view = new DataView(buf);
  const magic = String.fromCharCode(...new Uint8Array(buf, 0, 4));
  if (magic !== "SCYN" || view.getUint32(4, true) !== 1) throw new Error("not a Stitchcraft yarn path");
  const n = view.getUint32(8, true);
  const s = view.getUint32(12, true);
  let off = 20;
  const points = new Float32Array(buf.slice(off, off + n * 12));
  off += n * 12;
  const radius = new Float32Array(buf.slice(off, off + n * 4));
  off += n * 4;
  const stitchIds = new Uint32Array(buf.slice(off, off + n * 4));
  off += n * 4;
  const segmentOffsets = new Uint32Array(buf.slice(off, off + s * 4));
  return { count: n, points, radius, stitchIds, segmentOffsets };
}

/** Yarn point indices `start, start + step, …` up to and including `end` (the last point is always kept). */
export function pointIndices(start: number, end: number, step = 1): Uint32Array {
  const n = Math.floor((end - start) / step) + 1 + ((end - start) % step ? 1 : 0);
  const out = new Uint32Array(n);
  for (let j = 0; j < n; j++) out[j] = Math.min(start + j * step, end);
  return out;
}

/** Vertices per ring: the first one is repeated with u = 1, so the texture does not wrap backwards over the seam. */
export const ringSize = (sides: number) => sides + 1;

/** Parallel-transport frame and arc length at every yarn point, shared by all chunks and levels of detail. */
export interface Frames {
  tangent: Float32Array;
  normal: Float32Array;
  arc: Float64Array;
}

export function yarnFrames(yarn: Yarn): Frames {
  const n = yarn.count;
  const p = yarn.points;
  const tangent = new Float32Array(n * 3);
  const normal = new Float32Array(n * 3);
  const arc = new Float64Array(n);
  let nx = 0, ny = 0, nz = 0;
  for (let i = 0; i < n; i++) {
    const a = Math.max(i - 1, 0) * 3;
    const b = Math.min(i + 1, n - 1) * 3;
    let tx = p[b] - p[a], ty = p[b + 1] - p[a + 1], tz = p[b + 2] - p[a + 2];
    const tl = Math.hypot(tx, ty, tz) || 1;
    tx /= tl; ty /= tl; tz /= tl;
    if (i === 0) {
      // any vector perpendicular to the first tangent
      const ref = Math.abs(tz) < 0.9 ? [0, 0, 1] : [1, 0, 0];
      nx = ty * ref[2] - tz * ref[1];
      ny = tz * ref[0] - tx * ref[2];
      nz = tx * ref[1] - ty * ref[0];
    } else {
      const d = nx * tx + ny * ty + nz * tz;
      nx -= d * tx; ny -= d * ty; nz -= d * tz;
      arc[i] = arc[i - 1] + Math.hypot(p[i * 3] - p[i * 3 - 3], p[i * 3 + 1] - p[i * 3 - 2], p[i * 3 + 2] - p[i * 3 - 1]);
    }
    const nl = Math.hypot(nx, ny, nz) || 1;
    nx /= nl; ny /= nl; nz /= nl;
    tangent.set([tx, ty, tz], i * 3);
    normal.set([nx, ny, nz], i * 3);
  }
  return { tangent, normal, arc };
}

/**
 * Tube around the yarn centre line through the given points (default: all), one ring per point. uv: u around the
 * yarn (0–1), v along it in circumferences, so textures keep their aspect; v starts near 0 in every tube (an
 * integer shift, invisible in textures that repeat per tile) to keep float precision on long yarns.
 */
export function buildTube(yarn: Yarn, sides = 8, points = pointIndices(0, yarn.count - 1), frames = yarnFrames(yarn)): BufferGeometry {
  const n = points.length;
  const ring = ringSize(sides);
  const p = yarn.points;
  const { tangent: tg, normal: nm, arc } = frames;
  const pos = new Float32Array(n * ring * 3);
  const nor = new Float32Array(n * ring * 3);
  const uv = new Float32Array(n * ring * 2);
  const stitch = new Float32Array(n * ring);
  const vStart = n ? Math.floor(arc[points[0]] / (2 * Math.PI * (yarn.radius[points[0]] || 1))) : 0;
  for (let j = 0; j < n; j++) {
    const i = points[j];
    const tx = tg[i * 3], ty = tg[i * 3 + 1], tz = tg[i * 3 + 2];
    const nx = nm[i * 3], ny = nm[i * 3 + 1], nz = nm[i * 3 + 2];
    const bx = ty * nz - tz * ny, by = tz * nx - tx * nz, bz = tx * ny - ty * nx;
    const r = yarn.radius[i];
    const v = arc[i] / (2 * Math.PI * (r || 1)) - vStart; // ply twist repeats about once per circumference
    for (let k = 0; k < ring; k++) {
      const ang = (2 * Math.PI * k) / sides;
      const c = Math.cos(ang), s = Math.sin(ang);
      const ox = c * nx + s * bx, oy = c * ny + s * by, oz = c * nz + s * bz;
      const w = j * ring + k;
      pos[w * 3] = p[i * 3] + r * ox;
      pos[w * 3 + 1] = p[i * 3 + 1] + r * oy;
      pos[w * 3 + 2] = p[i * 3 + 2] + r * oz;
      nor[w * 3] = ox; nor[w * 3 + 1] = oy; nor[w * 3 + 2] = oz;
      uv[w * 2] = k / sides;
      uv[w * 2 + 1] = v;
      stitch[w] = yarn.stitchIds[i];
    }
  }
  const idx = new Uint32Array(Math.max(n - 1, 0) * sides * 6);
  let t = 0;
  for (let j = 0; j < n - 1; j++) {
    for (let k = 0; k < sides; k++) {
      const a = j * ring + k, b = a + 1;
      const c = a + ring, d = b + ring;
      idx.set([a, b, c, b, d, c], t);
      t += 6;
    }
  }
  const g = new BufferGeometry();
  g.setAttribute("position", new BufferAttribute(pos, 3));
  g.setAttribute("normal", new BufferAttribute(nor, 3));
  g.setAttribute("uv", new BufferAttribute(uv, 2));
  g.setAttribute("stitch", new BufferAttribute(stitch, 1));
  g.setIndex(new BufferAttribute(idx, 1));
  g.computeBoundingSphere();
  return g;
}

/** RGB per tube vertex (linear): the colour of each point's stitch, the selected stitch highlighted. */
export function vertexColors(
  yarn: Yarn, sides: number, colorOf: Map<number, string>, selected: number | null, highlight: string,
  points = pointIndices(0, yarn.count - 1),
): Float32Array {
  const ring = ringSize(sides);
  const out = new Float32Array(points.length * ring * 3);
  const cache = new Map<string, Color>();
  const color = (hex: string) => cache.get(hex) ?? cache.set(hex, new Color(hex)).get(hex)!;
  for (let j = 0; j < points.length; j++) {
    const id = yarn.stitchIds[points[j]];
    const c = color(id === selected ? highlight : (colorOf.get(id) ?? "#ffffff"));
    for (let k = 0; k < ring; k++) out.set([c.r, c.g, c.b], (j * ring + k) * 3);
  }
  return out;
}

/** Number of yarn points up to and including the last stitch of `maxRow` (yarn order). */
export function pointRangeForRows(yarn: Yarn, rowOf: Map<number, number>, maxRow: number): number {
  let last = 0;
  for (let i = 0; i < yarn.count; i++) {
    if ((rowOf.get(yarn.stitchIds[i]) ?? 0) <= maxRow) last = i + 1;
    else break;
  }
  return last;
}

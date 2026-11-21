import { BufferAttribute, BufferGeometry } from "three";

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

/** Tube around the yarn centre line, parallel-transport frames, one ring per point. */
export function buildTube(yarn: Yarn, sides = 8): BufferGeometry {
  const n = yarn.count;
  const p = yarn.points;
  const pos = new Float32Array(n * sides * 3);
  const nor = new Float32Array(n * sides * 3);
  const uv = new Float32Array(n * sides * 2);
  const stitch = new Float32Array(n * sides);
  let nx = 0, ny = 0, nz = 0;
  let arc = 0;
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
      arc += Math.hypot(p[i * 3] - p[i * 3 - 3], p[i * 3 + 1] - p[i * 3 - 2], p[i * 3 + 2] - p[i * 3 - 1]);
    }
    const nl = Math.hypot(nx, ny, nz) || 1;
    nx /= nl; ny /= nl; nz /= nl;
    const bx = ty * nz - tz * ny, by = tz * nx - tx * nz, bz = tx * ny - ty * nx;
    const r = yarn.radius[i];
    for (let k = 0; k < sides; k++) {
      const ang = (2 * Math.PI * k) / sides;
      const c = Math.cos(ang), s = Math.sin(ang);
      const ox = c * nx + s * bx, oy = c * ny + s * by, oz = c * nz + s * bz;
      const v = i * sides + k;
      pos[v * 3] = p[i * 3] + r * ox;
      pos[v * 3 + 1] = p[i * 3 + 1] + r * oy;
      pos[v * 3 + 2] = p[i * 3 + 2] + r * oz;
      nor[v * 3] = ox; nor[v * 3 + 1] = oy; nor[v * 3 + 2] = oz;
      uv[v * 2] = k / sides;
      uv[v * 2 + 1] = arc / (2 * Math.PI * (r || 1)); // ply twist repeats about once per circumference
      stitch[v] = yarn.stitchIds[i];
    }
  }
  const idx = new Uint32Array((n - 1) * sides * 6);
  let t = 0;
  for (let i = 0; i < n - 1; i++) {
    for (let k = 0; k < sides; k++) {
      const a = i * sides + k, b = i * sides + ((k + 1) % sides);
      const c = a + sides, d = b + sides;
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

/** Number of yarn points up to and including the last stitch of `maxRow` (yarn order). */
export function pointRangeForRows(yarn: Yarn, rowOf: Map<number, number>, maxRow: number): number {
  let last = 0;
  for (let i = 0; i < yarn.count; i++) {
    if ((rowOf.get(yarn.stitchIds[i]) ?? 0) <= maxRow) last = i + 1;
    else break;
  }
  return last;
}

import { DataTexture, LinearMipmapLinearFilter, RepeatWrapping } from "three";

/**
 * Ply twist as a tangent-space normal map over the tube's uv (u around the yarn, v along it in circumferences;
 * see buildTube). One tile is one circumference square, so the texture repeats seamlessly on every tube.
 */
export const PLY = {
  size: 256,
  plies: 4,
  /** Turns of the ply phase per circumference along the yarn: 3/4 gives a helix angle of about 37°. */
  twist: 3,
  /** Surface fibres per circumference; they run along the yarn, as in balanced plied yarn. */
  fibres: 48,
  /** Relief depth as a fraction of the yarn radius; MATERIAL_LOOK.normalScale scales it per material. */
  depth: 0.3,
} as const;

const fract = (x: number) => x - Math.floor(x);

/** Fixed pseudo-random value in [0, 1) per integer cell: no Math.random, so renders are reproducible. */
export function hash(n: number): number {
  let h = Math.imul(n ^ 0x9e3779b9, 0x85ebca6b);
  h = Math.imul(h ^ (h >>> 13), 0xc2b2ae35);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967296;
}

/** Relief height in [0, 1] at (u, v): rounded plies separated by grooves, fine fibres along the yarn on top. */
export function plyHeight(u: number, v: number): number {
  const phase = fract(PLY.plies * u + PLY.twist * v);
  const ply = Math.sin(Math.PI * phase) ** 0.6;
  // each fibre column gets its own strength, varying slowly (twice per tile) along the yarn
  const f = PLY.fibres * fract(u);
  const col = Math.floor(f) % PLY.fibres;
  const strength = 0.5 + 0.5 * Math.sin(2 * Math.PI * (2 * v + hash(col + 101)));
  const fibre = Math.sin(Math.PI * fract(f)) * (0.4 + 0.6 * hash(col + 7)) * strength;
  return 0.85 * ply + 0.15 * fibre;
}

/** RGBA bytes of the normal map, `size × size`, row y = v, column x = u. */
export function plyNormalData(size: number = PLY.size): Uint8Array {
  const h = new Float32Array(size * size);
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) h[y * size + x] = plyHeight(x / size, y / size);
  const at = (x: number, y: number) => h[((y + size) % size) * size + ((x + size) % size)];
  // slope = depth · r · dh / (2π r · du): u and v are both measured in circumferences
  const k = (PLY.depth * size) / (2 * Math.PI * 2);
  const out = new Uint8Array(size * size * 4);
  for (let y = 0; y < size; y++)
    for (let x = 0; x < size; x++) {
      const sx = (at(x + 1, y) - at(x - 1, y)) * k;
      const sy = (at(x, y + 1) - at(x, y - 1)) * k;
      const len = Math.hypot(sx, sy, 1);
      const i = (y * size + x) * 4;
      out[i] = Math.round(((-sx / len) * 0.5 + 0.5) * 255);
      out[i + 1] = Math.round(((-sy / len) * 0.5 + 0.5) * 255);
      out[i + 2] = Math.round(((1 / len) * 0.5 + 0.5) * 255);
      out[i + 3] = 255;
    }
  return out;
}

export function plyNormalMap(): DataTexture {
  const tex = new DataTexture(plyNormalData(), PLY.size, PLY.size);
  tex.wrapS = tex.wrapT = RepeatWrapping;
  tex.minFilter = LinearMipmapLinearFilter;
  tex.generateMipmaps = true;
  tex.anisotropy = 4;
  tex.needsUpdate = true;
  return tex;
}

import { DataTexture, MeshPhysicalMaterial, NearestFilter, RepeatWrapping } from "three";
import type { Material } from "../api";

/**
 * Fuzz shell: loose fibres around the yarn as stacked, slightly larger copies of the tube (shell texturing).
 * Each shell keeps only the fibre texels whose height lies near its own, so a fibre that lifts off the yarn climbs
 * from shell to shell.
 */
export interface FuzzLook {
  /** Number of shells; 0 turns the fuzz off. */
  shells: number;
  /** Outermost shell above the yarn surface, in yarn radii. */
  height: number;
  /** Fibres per tile (one circumference square of the tube's uv). */
  fibres: number;
  /** Fibre length range in tiles. */
  length: [number, number];
  opacity: number;
}

export const FUZZ: Record<Material, FuzzLook> = {
  mohair: { shells: 6, height: 1.2, fibres: 1000, length: [0.4, 1.2], opacity: 0.5 },
  cotton: { shells: 2, height: 0.15, fibres: 160, length: [0.05, 0.15], opacity: 0.5 },
  acrylic: { shells: 0, height: 0, fibres: 0, length: [0, 0], opacity: 0 },
};

export const FUZZ_TEXTURE_SIZE = 512;

/** Seeded PRNG (mulberry32): fibres are placed the same way on every run, so renders are reproducible. */
export function random(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * Fibre heights per texel (0 = no fibre, 1–255 = height above the yarn as a fraction of the fuzz height), tiling
 * seamlessly. Fibres mostly follow the yarn (v), each rises from the surface towards its end.
 */
export function fuzzHeights(look: FuzzLook, size = FUZZ_TEXTURE_SIZE, seed = 1): Uint8Array {
  const out = new Uint8Array(size * size);
  const rnd = random(seed);
  for (let f = 0; f < look.fibres; f++) {
    const u0 = rnd(), v0 = rnd();
    const angle = Math.PI / 2 + (rnd() - 0.5) * 1.4;
    const length = look.length[0] + rnd() * (look.length[1] - look.length[0]);
    const top = 0.35 + 0.65 * rnd();
    const bend = (rnd() - 0.5) * 1.2; // fibres curl a little
    const steps = Math.ceil(length * size * 2);
    for (let s = 0; s <= steps; s++) {
      const t = s / steps;
      const a = angle + bend * t;
      const x = Math.floor((u0 + Math.cos(a) * length * t) * size);
      const y = Math.floor((v0 + Math.sin(a) * length * t) * size);
      const i = (((y % size) + size) % size) * size + (((x % size) + size) % size);
      out[i] = Math.max(out[i], Math.max(1, Math.round(255 * top * t)));
    }
  }
  return out;
}

export function fuzzTexture(look: FuzzLook): DataTexture {
  const h = fuzzHeights(look);
  const rgba = new Uint8Array(h.length * 4);
  for (let i = 0; i < h.length; i++) rgba[i * 4] = rgba[i * 4 + 1] = rgba[i * 4 + 2] = rgba[i * 4 + 3] = h[i];
  const tex = new DataTexture(rgba, FUZZ_TEXTURE_SIZE, FUZZ_TEXTURE_SIZE);
  tex.wrapS = tex.wrapT = RepeatWrapping;
  // heights must not be blended: an averaged texel would land on a wrong shell
  tex.magFilter = tex.minFilter = NearestFilter;
  tex.needsUpdate = true;
  return tex;
}

/** Height of shell `i` of `n` (1-based) as a fraction of the fuzz height; each shell owns one band. */
export const shellLevel = (i: number, n: number) => i / n;

/**
 * Material of one shell: pushed out along the normal on the GPU; a fibre texel shows on the two shells around its
 * height, fading with the distance, so a rising fibre climbs smoothly from shell to shell.
 */
export function shellMaterial(look: FuzzLook, i: number, radius: number, map: DataTexture): MeshPhysicalMaterial {
  // translucent and without depth: thin fibres let light through, and the AO pass must not darken them like solid yarn;
  // sheen as on the yarn, fibres catch the light at grazing angles
  const m = new MeshPhysicalMaterial({
    vertexColors: true, roughness: 1, sheen: 1, sheenRoughness: 0.6, sheenColor: "#ffffff",
    transparent: true, opacity: look.opacity, depthWrite: false,
  });
  m.defines = { USE_UV: "" };
  const uniforms = {
    fuzzMap: { value: map },
    fuzzOffset: { value: shellLevel(i, look.shells) * look.height * radius },
    fuzzLevel: { value: shellLevel(i, look.shells) },
    fuzzBand: { value: 1 / look.shells },
  };
  m.onBeforeCompile = (shader) => {
    Object.assign(shader.uniforms, uniforms);
    shader.vertexShader = shader.vertexShader
      .replace("#include <common>", "#include <common>\nuniform float fuzzOffset;")
      .replace("#include <begin_vertex>", "#include <begin_vertex>\ntransformed += normal * fuzzOffset;");
    shader.fragmentShader = shader.fragmentShader
      .replace("#include <common>", "#include <common>\nuniform sampler2D fuzzMap;\nuniform float fuzzLevel;\nuniform float fuzzBand;")
      .replace(
        "#include <alphatest_fragment>",
        [
          "float fuzzH = texture2D(fuzzMap, vUv).g;",
          "float fuzzA = fuzzH == 0.0 ? 0.0 : 1.0 - abs(fuzzH - fuzzLevel) / fuzzBand;",
          "if (fuzzA <= 0.0) discard;",
          "diffuseColor.a *= fuzzA;",
        ].join("\n"),
      );
  };
  return m;
}

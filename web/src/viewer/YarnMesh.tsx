import { useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import { useEffect, useMemo } from "react";
import {
  BufferAttribute,
  Frustum,
  Group,
  Matrix4,
  Mesh,
  MeshBasicMaterial,
  MeshPhysicalMaterial,
  Vector2,
  Sphere,
  Vector3,
  type BufferGeometry,
  type DataTexture,
  type PerspectiveCamera,
} from "three";
import type { Material } from "../api";
import { FUZZ, fuzzHeights, shellCoverage, shellMaterial, shellTexture } from "./fuzz";
import { chunks, FAR, LEVELS, levelShells, LOD_MIN_POINTS, nextLevel, retained, visibleSegments, yarnPixels, type Chunk } from "./lod";
import { plyNormalMap } from "./ply";
import { buildTube, pointIndices, vertexColors, yarnFrames, type Yarn } from "./yarn";

/**
 * Surface look per yarn material: shading, strength of the ply normal map; the fuzz shell is in FUZZ.
 * Any change to the look: bump data/render.json, or the MCP serves cached PNGs of the old one.
 */
export const MATERIAL_LOOK: Record<Material, { roughness: number; sheen: number; sheenRoughness: number; normalScale: number }> = {
  cotton: { roughness: 0.85, sheen: 0.6, sheenRoughness: 0.45, normalScale: 1 },
  acrylic: { roughness: 0.5, sheen: 0.25, sheenRoughness: 0.3, normalScale: 0.7 },
  mohair: { roughness: 1, sheen: 1, sheenRoughness: 0.9, normalScale: 0.35 },
};

const HIGHLIGHT = "#e0533d";
/** Level switches that build new geometry per frame, so zooming into a large piece does not stall. */
const BUILDS_PER_FRAME = 12;

/** A tube through some of a chunk's points. */
interface Tube {
  points: Uint32Array;
  sides: number;
  geometry: BufferGeometry;
}

interface Built {
  tube: Tube;
  core: Mesh;
  /** Coarser tube for the fuzz shells, built while they are shown. */
  shellTube?: Tube;
  shells: Mesh[];
}

const dispose = (b: Built | undefined) => (b?.tube.geometry.dispose(), b?.shellTube?.geometry.dispose());

interface ChunkState extends Chunk {
  index: number;
  group: Group;
  level: number;
  built: (Built | undefined)[];
}

interface Props {
  yarn: Yarn;
  material: Material;
  colorOf: Map<number, string>;
  selected: number | null;
  silhouette: boolean;
  fuzz: boolean;
  /** Yarn points shown (row slider). */
  visiblePoints: number;
  centre: Vector3;
  onSelect(id: number): void;
}

const noRaycast = () => undefined;

/** The yarn as chunked tubes; each chunk switches between the levels of lod.ts as the camera moves. */
export function YarnMesh({ yarn, material, colorOf, selected, silhouette, fuzz, visiblePoints, centre, onSelect }: Props) {
  const camera = useThree((s) => s.camera) as PerspectiveCamera;
  const gl = useThree((s) => s.gl);
  const radius = yarn.radius[0] ?? 1;

  const ply = useMemo(plyNormalMap, []);
  const look = MATERIAL_LOOK[material];
  const surface = useMemo(() => new MeshPhysicalMaterial({ vertexColors: true, sheenColor: "#d8d8d8", normalMap: ply }), [ply]);
  const black = useMemo(() => new MeshBasicMaterial({ color: "black" }), []);
  useEffect(() => {
    surface.roughness = look.roughness;
    surface.sheen = look.sheen;
    surface.sheenRoughness = look.sheenRoughness;
    surface.normalScale = new Vector2(look.normalScale, look.normalScale);
  }, [surface, look]);
  const fuzzLook = FUZZ[material];
  // shell materials per level (levels draw different numbers of shells over the same height), one coverage texture each
  const { shellMaterials, textures } = useMemo(() => {
    if (!fuzzLook.shells) return { shellMaterials: LEVELS.map(() => []), textures: [] };
    const heights = fuzzHeights(fuzzLook);
    const textures: DataTexture[] = [];
    const sets = new Map<number, MeshPhysicalMaterial[]>();
    const set = (n: number) => {
      if (!sets.has(n))
        sets.set(n, Array.from({ length: n }, (_, i) => {
          const tex = shellTexture(shellCoverage(heights, i + 1, n));
          textures.push(tex);
          return shellMaterial({ ...fuzzLook, shells: n }, i + 1, radius, tex);
        }));
      return sets.get(n)!;
    };
    return { shellMaterials: LEVELS.map((_, level) => set(levelShells(level, fuzzLook.shells))), textures };
  }, [fuzzLook, radius]);
  useEffect(
    () => () => (textures.forEach((t) => t.dispose()), new Set(shellMaterials.flat()).forEach((m) => m.dispose())),
    [textures, shellMaterials],
  );
  useEffect(() => () => (ply.dispose(), surface.dispose(), black.dispose()), [ply, surface, black]);

  const state = useMemo(() => {
    const root = new Group();
    root.position.copy(centre).negate();
    const frames = yarnFrames(yarn);
    const list: ChunkState[] = chunks(yarn).map((c, index) => {
      const group = new Group();
      root.add(group);
      return { ...c, index, group, level: -1, built: [] };
    });
    // e2e hook: bytes held by all built tubes (CPU side; the GPU holds a copy of the same buffers)
    root.userData.tubeBytes = () => {
      let bytes = 0;
      for (const c of list)
        for (const b of c.built)
          for (const g of b ? [b.tube.geometry, b.shellTube?.geometry] : [])
            if (g) for (const a of [...Object.values(g.attributes), g.index!]) bytes += a.array.byteLength;
      return bytes;
    };
    return { root, list, frames };
  }, [yarn, centre]);
  useEffect(
    () => () => state.list.forEach((c) => c.built.forEach(dispose)),
    [state],
  );

  // everything a level's meshes depend on besides the camera; read by build() and the effects below
  const shown = { colorOf, selected, visiblePoints, silhouette, fuzz, shellMaterials, surface, black, fuzzReach: fuzzLook.height * radius };

  const paint = (t: Tube) => {
    const rgb = vertexColors(yarn, t.sides, shown.colorOf, shown.selected, HIGHLIGHT, t.points);
    const attr = t.geometry.getAttribute("color") as BufferAttribute | undefined;
    if (!attr) return void t.geometry.setAttribute("color", new BufferAttribute(rgb, 3));
    (attr.array as Float32Array).set(rgb); // reuse the GPU buffer
    attr.needsUpdate = true;
  };
  const clip = (t: Tube) => t.geometry.setDrawRange(0, visibleSegments(t.points, shown.visiblePoints) * t.sides * 6);
  const tube = (c: ChunkState, sides: number, step: number): Tube => {
    const points = pointIndices(c.start, c.end, step);
    const t = { points, sides, geometry: buildTube(yarn, sides, points, state.frames) };
    paint(t);
    clip(t);
    return t;
  };
  const tubes = (b: Built) => (b.shellTube ? [b.tube, b.shellTube] : [b.tube]);
  const dress = (c: ChunkState, b: Built, level: number) => {
    b.core.material = shown.silhouette ? shown.black : shown.surface;
    const materials = shown.fuzz && !shown.silhouette ? shown.shellMaterials[level] : [];
    b.shells.forEach((s) => s.removeFromParent());
    if (!materials.length) {
      b.shellTube?.geometry.dispose();
      b.shellTube = undefined;
      b.shells = [];
      return;
    }
    if (!b.shellTube) {
      b.shellTube = tube(c, LEVELS[level].shellSides, LEVELS[level].shellStep);
      // the shells reach further out than the tube: keep them from being culled at the edge of the view
      b.shellTube.geometry.boundingSphere!.radius += shown.fuzzReach;
    }
    // blending order inner to outer shell, then by chunk: fixed, whatever order the meshes were created in
    const order = (shell: number) => shell * state.list.length + c.index;
    b.shells = materials.map((m, i) => Object.assign(new Mesh(b.shellTube!.geometry, m), { raycast: noRaycast, renderOrder: order(i + 1) }));
    b.shells.forEach((s) => b.core.add(s));
  };
  const build = (c: ChunkState, level: number): Built => {
    const t = tube(c, LEVELS[level].sides, LEVELS[level].step);
    const core = new Mesh(t.geometry);
    core.userData = { yarn: true, level };
    const b: Built = { tube: t, core, shells: [] };
    dress(c, b, level);
    return b;
  };

  useEffect(() => state.list.forEach((c) => c.built.forEach((b) => b && tubes(b).forEach(paint))), [state, colorOf, selected]);
  useEffect(() => state.list.forEach((c) => c.built.forEach((b) => b && tubes(b).forEach(clip))), [state, visiblePoints]);
  useEffect(
    () => state.list.forEach((c) => c.built.forEach((b, level) => b && dress(c, b, level))),
    [state, silhouette, fuzz, shellMaterials, surface, black],
  );

  const eye = useMemo(() => new Vector3(), []);
  const size = useMemo(() => new Vector2(), []);
  const view = useMemo(() => ({ frustum: new Frustum(), matrix: new Matrix4(), sphere: new Sphere() }), []);
  useFrame(() => {
    gl.getDrawingBufferSize(size);
    camera.updateMatrixWorld();
    view.frustum.setFromProjectionMatrix(view.matrix.multiplyMatrices(camera.projectionMatrix, camera.matrixWorldInverse));
    eye.copy(camera.position).add(centre); // camera in yarn coordinates
    const coarsest = yarn.count > LOD_MIN_POINTS ? FAR : FAR - 1;
    let builds = 0;
    for (const c of state.list) {
      // chunks out of view keep only the coarsest level, so their detail does not pile up in memory
      view.sphere.center.set(c.centre[0], c.centre[1], c.centre[2]).sub(centre);
      view.sphere.radius = c.radius + shown.fuzzReach;
      const d = Math.hypot(eye.x - c.centre[0], eye.y - c.centre[1], eye.z - c.centre[2]) - c.radius;
      const px = view.frustum.intersectsSphere(view.sphere) ? yarnPixels(radius, d, camera.fov, size.y) : 0;
      const level = nextLevel(c.level, px, coarsest);
      if (level === c.level) continue;
      // the first level of every chunk is built at once, later switches are spread over frames
      if (!c.built[level]) {
        if (c.level !== -1 && builds >= BUILDS_PER_FRAME) continue;
        c.built[level] = build(c, level);
        builds++;
      }
      c.group.clear();
      c.group.add(c.built[level]!.core);
      c.level = level;
      // keep the level shown and its neighbours (cheap to switch back), free the rest
      c.built.forEach((b, l) => {
        if (b && !retained(level, l)) (dispose(b), (c.built[l] = undefined));
      });
    }
  });

  const pick = (e: ThreeEvent<PointerEvent>) => {
    const geometry = (e.object as Mesh).geometry;
    if (e.faceIndex == null || !geometry.index) return;
    e.stopPropagation();
    onSelect(geometry.getAttribute("stitch").getX(geometry.index.getX(e.faceIndex * 3)));
  };

  return <primitive object={state.root} onPointerDown={pick} />;
}


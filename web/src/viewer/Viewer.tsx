import { Environment, Lightformer, OrbitControls, Stats } from "@react-three/drei";
import { Canvas, useThree, type ThreeEvent } from "@react-three/fiber";
import { EffectComposer, N8AO } from "@react-three/postprocessing";
import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef } from "react";
import {
  BufferAttribute,
  CanvasTexture,
  RepeatWrapping,
  Raycaster,
  Vector2,
  Vector3,
  type BufferGeometry,
  type Mesh,
  type PerspectiveCamera,
} from "three";
import type { Material } from "../api";
import { buildTube, pointRangeForRows, vertexColors, type Yarn } from "./yarn";

/** Surface look per yarn material; fuzz geometry is a later milestone. */
export const MATERIAL_LOOK: Record<Material, { roughness: number; sheen: number; sheenRoughness: number; bumpScale: number }> = {
  cotton: { roughness: 0.85, sheen: 0.6, sheenRoughness: 0.45, bumpScale: 0.6 },
  acrylic: { roughness: 0.5, sheen: 0.25, sheenRoughness: 0.3, bumpScale: 0.4 },
  mohair: { roughness: 1, sheen: 1, sheenRoughness: 0.9, bumpScale: 0.9 },
};

export type View = "front" | "side" | "top" | "iso";
type Controls = { target: Vector3; update(): void };
const SIDES = 8;
const HIGHLIGHT = "#e0533d";

export interface ViewerHandle {
  snapshot(): string;
}

interface Props {
  yarn: Yarn;
  rowOf: Map<number, number>;
  maxRow: number;
  colorOf: Map<number, string>; // stitch id -> "#rrggbb"
  selected: number | null;
  onSelect(id: number): void;
  silhouette: boolean;
  view: View;
  rounds: boolean;
  material: Material;
  showFps: boolean;
}

/** Ply twist as a bump map: diagonal stripes along the tube's (around, along) uv. */
function plyTexture(): CanvasTexture {
  const size = 64;
  const c = document.createElement("canvas");
  c.width = c.height = size;
  const ctx = c.getContext("2d")!;
  const img = ctx.createImageData(size, size);
  for (let y = 0; y < size; y++)
    for (let x = 0; x < size; x++) {
      const v = 0.5 + 0.5 * Math.sin(((x + y) / size) * 2 * Math.PI * 3);
      const i = (y * size + x) * 4;
      img.data[i] = img.data[i + 1] = img.data[i + 2] = Math.round(255 * v ** 0.6);
      img.data[i + 3] = 255;
    }
  ctx.putImageData(img, 0, 0);
  const tex = new CanvasTexture(c);
  tex.wrapS = tex.wrapT = RepeatWrapping;
  return tex;
}

function viewDirection(view: View, rounds: boolean): [Vector3, Vector3] {
  // rounds grow along +z; flat pieces lie in the xy plane with the front towards +z
  const up = new Vector3(0, 0, 1);
  if (rounds) {
    switch (view) {
      case "front": return [new Vector3(0, -1, 0.15), up];
      case "side": return [new Vector3(1, 0, 0.15), up];
      case "top": return [new Vector3(0, 0.001, 1), new Vector3(0, 1, 0)];
      default: return [new Vector3(1, -1, 0.8), up];
    }
  }
  const yUp = new Vector3(0, 1, 0);
  switch (view) {
    case "front": return [new Vector3(0, 0, 1), yUp];
    case "side": return [new Vector3(1, 0, 0.001), new Vector3(0, 0, 1)];
    case "top": return [new Vector3(0, 1, 0.001), new Vector3(0, 0, 1)];
    default: return [new Vector3(0.8, -0.8, 1), yUp];
  }
}

function CameraRig({ radius, view, rounds }: { radius: number; view: View; rounds: boolean }) {
  const camera = useThree((s) => s.camera) as PerspectiveCamera;
  const controls = useThree((s) => s.controls) as unknown as Controls | null;
  useEffect(() => {
    const [dir, up] = viewDirection(view, rounds);
    const dist = (radius / Math.sin(((camera.fov / 2) * Math.PI) / 180)) * 1.15;
    camera.up.copy(up);
    camera.position.copy(dir.normalize().multiplyScalar(dist));
    camera.near = dist / 100;
    camera.far = dist * 10;
    camera.updateProjectionMatrix();
    controls?.target.set(0, 0, 0);
    controls?.update();
  }, [camera, controls, radius, view, rounds]);
  return null;
}

/** Test hook (`?e2e`): client coordinates and stitch id of a visible yarn pixel, found by raycasting a grid from the centre outwards. */
function E2eHook() {
  const { scene, camera, gl } = useThree();
  useEffect(() => {
    const hook = {
      hitPoint() {
        const mesh = scene.children.find((o) => (o as Mesh).isMesh) as Mesh | undefined;
        if (!mesh) return null;
        const rect = gl.domElement.getBoundingClientRect();
        const ray = new Raycaster();
        const geometry = mesh.geometry;
        const spots: [number, number][] = [];
        for (let i = -9; i <= 9; i++) for (let j = -9; j <= 9; j++) spots.push([i / 10, j / 10]);
        spots.sort((a, b) => Math.hypot(...a) - Math.hypot(...b));
        for (const [nx, ny] of spots) {
          ray.setFromCamera(new Vector2(nx, ny), camera);
          const hit = ray.intersectObject(mesh)[0];
          if (hit?.faceIndex != null && geometry.index)
            return {
              x: rect.left + ((nx + 1) / 2) * rect.width,
              y: rect.top + ((1 - ny) / 2) * rect.height,
              stitch: geometry.getAttribute("stitch").getX(geometry.index.getX(hit.faceIndex * 3)),
            };
        }
        return null;
      },
      /** Unit vector from the orbit target to the camera. */
      cameraDirection() {
        return camera.position.clone().normalize().toArray();
      },
    };
    (window as unknown as { __stitchcraft?: typeof hook }).__stitchcraft = hook;
    return () => void delete (window as unknown as { __stitchcraft?: typeof hook }).__stitchcraft;
  }, [scene, camera, gl]);
  return null;
}

function YarnMesh({ geometry, material, yarn, colorOf, silhouette, selected, onSelect, drawCount, centre }: {
  geometry: BufferGeometry; material: Material; yarn: Yarn; colorOf: Map<number, string>; silhouette: boolean; selected: number | null;
  onSelect(id: number): void; drawCount: number; centre: Vector3;
}) {
  const ply = useMemo(plyTexture, []);
  const look = MATERIAL_LOOK[material];
  useEffect(() => {
    geometry.setDrawRange(0, drawCount);
  }, [geometry, drawCount]);
  useEffect(() => {
    const rgb = vertexColors(yarn, SIDES, colorOf, selected, HIGHLIGHT);
    const attr = geometry.getAttribute("color") as BufferAttribute | undefined;
    if (!attr) return void geometry.setAttribute("color", new BufferAttribute(rgb, 3));
    (attr.array as Float32Array).set(rgb); // reuse the GPU buffer
    attr.needsUpdate = true;
  }, [geometry, yarn, colorOf, selected]);

  const pick = (e: ThreeEvent<PointerEvent>) => {
    if (e.faceIndex == null || !geometry.index) return;
    e.stopPropagation();
    const vertex = geometry.index.getX(e.faceIndex * 3);
    onSelect(geometry.getAttribute("stitch").getX(vertex));
  };

  return (
    <mesh geometry={geometry} position={centre.clone().negate()} onPointerDown={pick}>
      {silhouette ? (
        <meshBasicMaterial color="black" />
      ) : (
        <meshPhysicalMaterial
          vertexColors
          roughness={look.roughness}
          sheen={look.sheen}
          sheenRoughness={look.sheenRoughness}
          sheenColor="#d8d8d8"
          bumpMap={ply}
          bumpScale={look.bumpScale}
        />
      )}
    </mesh>
  );
}

export const Viewer = forwardRef<ViewerHandle, Props>(function Viewer(props, ref) {
  const { yarn, rowOf, maxRow, colorOf, selected, onSelect, silhouette, view, rounds, material, showFps } = props;
  const canvas = useRef<HTMLCanvasElement>(null);
  useImperativeHandle(ref, () => ({ snapshot: () => canvas.current?.toDataURL("image/png") ?? "" }));

  const geometry = useMemo(() => buildTube(yarn, SIDES), [yarn]);
  useEffect(() => () => geometry.dispose(), [geometry]);
  const { centre, radius } = useMemo(() => {
    geometry.computeBoundingBox();
    const box = geometry.boundingBox!;
    const c = box.getCenter(new Vector3());
    return { centre: c, radius: box.getSize(new Vector3()).length() / 2 };
  }, [geometry]);
  const points = pointRangeForRows(yarn, rowOf, maxRow);
  const drawCount = Math.max(points - 1, 0) * SIDES * 6;

  return (
    <Canvas
      ref={canvas}
      camera={{ fov: 30 }}
      gl={{ preserveDrawingBuffer: true, antialias: true }}
      dpr={[1, 2]}
      style={{ background: silhouette ? "#ffffff" : "var(--viewer-bg)" }}
    >
      {showFps && <Stats />}
      {new URLSearchParams(location.search).has("e2e") && <E2eHook />}
      <CameraRig radius={radius} view={view} rounds={rounds} />
      <OrbitControls makeDefault enableDamping />
      {!silhouette && (
        <>
          <ambientLight intensity={0.25} />
          <directionalLight position={[radius * 2, -radius * 2, radius * 3]} intensity={1.4} />
          <Environment resolution={256}>
            <Lightformer form="rect" intensity={2} position={[0, 0, 5]} scale={[10, 5, 1]} />
            <Lightformer form="rect" intensity={1} position={[-5, 2, 1]} rotation-y={Math.PI / 2} scale={[10, 3, 1]} />
            <Lightformer form="ring" intensity={0.8} position={[4, -3, 2]} scale={3} />
          </Environment>
        </>
      )}
      <YarnMesh
        geometry={geometry}
        material={material}
        yarn={yarn}
        colorOf={colorOf}
        silhouette={silhouette}
        selected={selected}
        onSelect={onSelect}
        drawCount={drawCount}
        centre={centre}
      />
      {!silhouette && (
        <EffectComposer>
          <N8AO aoRadius={radius / 25} distanceFalloff={0.5} intensity={3} />
        </EffectComposer>
      )}
    </Canvas>
  );
});

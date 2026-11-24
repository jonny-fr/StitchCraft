import { Environment, Lightformer, OrbitControls, Stats } from "@react-three/drei";
import { Canvas, useThree } from "@react-three/fiber";
import { EffectComposer, N8AO } from "@react-three/postprocessing";
import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef } from "react";
import { Box3, Raycaster, Vector2, Vector3, type Intersection, type Mesh, type PerspectiveCamera } from "three";
import type { Material } from "../api";
import { LEVELS } from "./lod";
import { pointRangeForRows, type Yarn } from "./yarn";
import { YarnMesh } from "./YarnMesh";

export type View = "front" | "side" | "top" | "iso";
type Controls = { target: Vector3; update(): void };

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
  /** Fuzz shell around the yarn (strength per material, see fuzz.ts). */
  fuzz: boolean;
  showFps: boolean;
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
  const controls = useThree((s) => s.controls) as unknown as Controls | null;
  useEffect(() => {
    // nearest hit on a yarn tube (not on a fuzz shell) at normalised device coordinates
    const yarnHit = (at: Vector2): Intersection | undefined => {
      const ray = new Raycaster();
      ray.setFromCamera(at, camera);
      return ray.intersectObjects(scene.children, true).find((h) => h.object.userData.yarn);
    };
    const hook = {
      hitPoint() {
        const rect = gl.domElement.getBoundingClientRect();
        const spots: [number, number][] = [];
        for (let i = -9; i <= 9; i++) for (let j = -9; j <= 9; j++) spots.push([i / 10, j / 10]);
        spots.sort((a, b) => Math.hypot(...a) - Math.hypot(...b));
        for (const [nx, ny] of spots) {
          const hit = yarnHit(new Vector2(nx, ny));
          const geometry = (hit?.object as Mesh | undefined)?.geometry;
          if (hit?.faceIndex != null && geometry?.index)
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
      /** Shown yarn chunks per level of detail (lod.ts), how many of them draw fuzz shells, bytes of all built tubes. */
      levels() {
        const chunks = LEVELS.map(() => 0);
        let fuzz = 0;
        let bytes = 0;
        scene.traverseVisible((o) => {
          if (o.userData.tubeBytes) bytes = (o.userData.tubeBytes as () => number)();
          if (!o.userData.yarn) return;
          chunks[o.userData.level as number]++;
          if (o.children.length) fuzz++;
        });
        return { chunks, fuzz, bytes };
      },
      /** Close-up: orbits around the yarn under the canvas centre, `mm` away from it; false when the centre shows no yarn. */
      closeUp(mm: number) {
        const hit = yarnHit(new Vector2(0, 0));
        if (!hit) return false;
        camera.position.sub(hit.point).setLength(mm).add(hit.point);
        (camera as PerspectiveCamera).near = mm / 100;
        camera.updateProjectionMatrix();
        controls?.target.copy(hit.point);
        controls?.update();
        return true;
      },
    };
    (window as unknown as { __stitchcraft?: typeof hook }).__stitchcraft = hook;
    return () => void delete (window as unknown as { __stitchcraft?: typeof hook }).__stitchcraft;
  }, [scene, camera, gl, controls]);
  return null;
}

export const Viewer = forwardRef<ViewerHandle, Props>(function Viewer(props, ref) {
  const { yarn, rowOf, maxRow, colorOf, selected, onSelect, silhouette, view, rounds, material, fuzz, showFps } = props;
  const canvas = useRef<HTMLCanvasElement>(null);
  useImperativeHandle(ref, () => ({ snapshot: () => canvas.current?.toDataURL("image/png") ?? "" }));

  const { centre, radius } = useMemo(() => {
    const box = new Box3().setFromArray(yarn.points).expandByScalar(yarn.radius[0] ?? 0);
    return { centre: box.getCenter(new Vector3()), radius: box.getSize(new Vector3()).length() / 2 };
  }, [yarn]);

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
        yarn={yarn}
        material={material}
        colorOf={colorOf}
        selected={selected}
        silhouette={silhouette}
        fuzz={fuzz}
        visiblePoints={pointRangeForRows(yarn, rowOf, maxRow)}
        centre={centre}
        onSelect={onSelect}
      />
      {!silhouette && (
        <EffectComposer>
          <N8AO aoRadius={radius / 25} distanceFalloff={0.5} intensity={3} />
        </EffectComposer>
      )}
    </Canvas>
  );
});

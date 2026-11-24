import { describe, expect, it } from "vitest";
import { PLY, plyHeight, plyNormalData } from "./ply";

const SIZE = 64;
const decode = (d: Uint8Array, x: number, y: number) => {
  const i = (y * SIZE + x) * 4;
  return [d[i], d[i + 1], d[i + 2]].map((c) => (c / 255) * 2 - 1);
};

describe("ply normal map", () => {
  const data = plyNormalData(SIZE);

  it("is deterministic", () => {
    expect(plyNormalData(SIZE)).toEqual(data);
  });

  it("holds unit tangent-space normals that face outwards", () => {
    for (let y = 0; y < SIZE; y += 7)
      for (let x = 0; x < SIZE; x += 5) {
        const [nx, ny, nz] = decode(data, x, y);
        expect(Math.hypot(nx, ny, nz)).toBeCloseTo(1, 1);
        expect(nz).toBeGreaterThan(0.3);
      }
  });

  it("tiles seamlessly around and along the yarn", () => {
    const step = (a: number, b: number) => Math.abs(plyHeight(a, 0.3) - plyHeight(b, 0.3));
    expect(Math.abs(plyHeight(0, 0.3) - plyHeight(1, 0.3))).toBeLessThan(1e-9);
    expect(Math.abs(plyHeight(0.2, 0) - plyHeight(0.2, 1))).toBeLessThan(1e-9);
    expect(step(1 - 1 / SIZE, 1)).toBeLessThan(0.5);
  });

  it("shows the plies as grooves that wind diagonally around the yarn", () => {
    // grooves: where the relief dips low, as start positions along one ring
    const grooves = (v: number) => {
      const n = 512;
      const low = Array.from({ length: n }, (_, i) => plyHeight(i / n, v) < 0.3);
      return low.flatMap((x, i) => (x && !low[(i + n - 1) % n] ? [i / n] : []));
    };
    expect(grooves(0)).toHaveLength(PLY.plies);
    // a little further along the yarn the grooves have turned: the plies are twisted, not parallel to the axis
    const shift = grooves(0.05)[0] - grooves(0)[0];
    expect(Math.abs(shift)).toBeGreaterThan(0.02);
  });
});

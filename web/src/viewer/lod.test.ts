import { describe, expect, it } from "vitest";
import { chunks, FAR, LEVELS, levelShells, nextLevel, retained, visibleSegments, yarnPixels } from "./lod";
import type { Yarn } from "./yarn";

function line(n: number): Yarn {
  const points = new Float32Array(n * 3);
  for (let i = 0; i < n; i++) points.set([i, Math.sin(i), 0], i * 3);
  return { count: n, points, radius: new Float32Array(n).fill(0.5), stitchIds: new Uint32Array(n), segmentOffsets: new Uint32Array([0]) };
}

describe("chunks", () => {
  it("cover every point, neighbours share their boundary point", () => {
    const c = chunks(line(25), 10);
    expect(c.map((k) => [k.start, k.end])).toEqual([[0, 10], [10, 20], [20, 24]]);
    expect(chunks(line(1), 10).map((k) => [k.start, k.end])).toEqual([[0, 0]]);
  });

  it("have bounding spheres around all their points and the yarn radius", () => {
    const yarn = line(25);
    for (const k of chunks(yarn, 10))
      for (let i = k.start; i <= k.end; i++) {
        const d = Math.hypot(yarn.points[i * 3] - k.centre[0], yarn.points[i * 3 + 1] - k.centre[1], yarn.points[i * 3 + 2] - k.centre[2]);
        expect(d + 0.5).toBeLessThanOrEqual(k.radius + 1e-6);
      }
  });
});

describe("level of detail", () => {
  it("measures the yarn in device pixels", () => {
    // 30° field of view at the distance where the view is 100 mm high
    const distance = 50 / Math.tan(Math.PI / 12);
    expect(yarnPixels(0.5, distance, 30, 1000)).toBeCloseTo(10, 6);
    expect(yarnPixels(0.5, distance / 2, 30, 1000)).toBeCloseTo(20, 6);
  });

  it("goes from full tubes with fuzz in close-ups to coarse tubes without fuzz far away", () => {
    expect(nextLevel(-1, 100)).toBe(0);
    expect(nextLevel(-1, 20)).toBe(1);
    expect(nextLevel(-1, 3)).toBe(FAR);
    expect(LEVELS[0].sides).toBeGreaterThan(LEVELS[FAR].sides);
    expect(levelShells(0, 6)).toBe(6);
    expect(levelShells(1, 6)).toBeGreaterThan(0);
    expect(levelShells(1, 6)).toBeLessThan(6);
    expect(levelShells(FAR, 6)).toBe(0);
    expect(LEVELS[FAR].step).toBeGreaterThan(1);
  });

  it("switches back only below the leave threshold, so the level does not flicker", () => {
    const near = LEVELS[1];
    const between = (near.enter + near.leave) / 2;
    expect(nextLevel(1, between)).toBe(1);
    expect(nextLevel(FAR, between)).toBe(FAR);
    expect(nextLevel(1, near.leave - 0.1)).toBe(FAR);
    expect(nextLevel(FAR, near.enter)).toBe(1);
  });

  it("never goes coarser than allowed (small pieces stay near)", () => {
    expect(nextLevel(-1, 1, FAR - 1)).toBe(FAR - 1);
    expect(nextLevel(1, 1, FAR - 1)).toBe(1);
  });

  it("depends only on its inputs (same camera, same levels)", () => {
    const px = [3, 8, 12, 9, 40, 60, 30, 6];
    const run = () => px.reduce<number[]>((acc, p) => [...acc, nextLevel(acc.at(-1) ?? -1, p)], []);
    expect(run()).toEqual(run());
  });
});

describe("retained", () => {
  it("keeps the shown level and its neighbours, frees the rest", () => {
    expect(retained(0, 0)).toBe(true);
    expect(retained(0, 1)).toBe(true);
    expect(retained(0, FAR)).toBe(FAR <= 1);
    expect(retained(FAR, 0)).toBe(FAR <= 1);
    expect(retained(1, 0) && retained(1, FAR)).toBe(true);
  });
});

describe("visibleSegments", () => {
  it("counts the segments up to the last shown point (row slider)", () => {
    const points = [10, 12, 14, 15];
    expect(visibleSegments(points, 100)).toBe(3);
    expect(visibleSegments(points, 15)).toBe(2);
    expect(visibleSegments(points, 13)).toBe(1);
    expect(visibleSegments(points, 10)).toBe(0);
  });
});

import { ShaderLib } from "three";
import { describe, expect, it } from "vitest";
import { FUZZ, fuzzHeights, random, shellLevel, shellMaterial, fuzzTexture } from "./fuzz";

const coverage = (h: Uint8Array) => h.reduce((n, x) => n + (x > 0 ? 1 : 0), 0) / h.length;

describe("fuzz", () => {
  it("places fibres the same way on every run", () => {
    expect(fuzzHeights(FUZZ.mohair)).toEqual(fuzzHeights(FUZZ.mohair));
    expect(fuzzHeights(FUZZ.mohair, 512, 2)).not.toEqual(fuzzHeights(FUZZ.mohair));
    expect(random(7)()).toBe(random(7)());
  });

  it("is strong for mohair, subtle for cotton and off for acrylic", () => {
    expect(coverage(fuzzHeights(FUZZ.mohair))).toBeGreaterThan(3 * coverage(fuzzHeights(FUZZ.cotton)));
    expect(coverage(fuzzHeights(FUZZ.cotton))).toBeGreaterThan(0);
    expect(FUZZ.acrylic.shells).toBe(0);
    expect(FUZZ.mohair.height).toBeGreaterThan(5 * FUZZ.cotton.height);
  });

  it("lets fibres rise from the yarn, so every shell gets some of them", () => {
    const h = fuzzHeights(FUZZ.mohair);
    const n = FUZZ.mohair.shells;
    for (let i = 1; i <= n; i++) {
      const level = shellLevel(i, n);
      const band = h.filter((x) => x > 0 && Math.abs(x / 255 - level) < 1 / n);
      expect(band.length, `shell ${i}`).toBeGreaterThan(0);
    }
  });

  it("pushes each shell out along the normal on the GPU and keeps only its height band", () => {
    const look = FUZZ.mohair;
    const m = shellMaterial(look, look.shells, 0.6, fuzzTexture(look));
    // the anchors must exist in three's physical shader, or the injection would silently do nothing
    const shader = { uniforms: {}, vertexShader: ShaderLib.physical.vertexShader, fragmentShader: ShaderLib.physical.fragmentShader };
    m.onBeforeCompile(shader as never, undefined as never);
    expect(shader.vertexShader).toContain("transformed += normal * fuzzOffset;");
    expect(shader.fragmentShader).toContain("discard;");
    expect(shader.fragmentShader).not.toContain("#include <alphatest_fragment>");
    const u = shader.uniforms as Record<string, { value: number }>;
    expect(u.fuzzOffset.value).toBeCloseTo(look.height * 0.6, 6);
    expect(u.fuzzLevel.value).toBe(1);
    expect(m.depthWrite).toBe(false);
  });
});

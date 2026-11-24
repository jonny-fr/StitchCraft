import { ShaderLib } from "three";
import { describe, expect, it } from "vitest";
import { FUZZ, fuzzHeights, random, shellCoverage, shellMaterial, shellTexture } from "./fuzz";

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
    for (let i = 1; i <= n; i++) expect(coverage(shellCoverage(h, i, n)), `shell ${i}`).toBeGreaterThan(0);
  });

  it("splits each fibre texel over the two shells around its height", () => {
    const n = 4;
    const h = new Uint8Array([0, 255, Math.round(255 * 0.375)]);
    const shells = [1, 2, 3, 4].map((i) => Array.from(shellCoverage(h, i, n)));
    expect(shells.map((c) => c[0])).toEqual([0, 0, 0, 0]); // no fibre
    expect(shells.map((c) => c[1])).toEqual([0, 0, 0, 255]); // at the top: outermost shell only
    // between shells 1 (0.25) and 2 (0.5): half on each
    expect(shells[0][2] + shells[1][2]).toBeGreaterThan(250);
    expect(shells[2][2] + shells[3][2]).toBe(0);
  });

  it("filters coverage with mipmaps, so distant fibres blend into a haze instead of speckle", () => {
    const tex = shellTexture(shellCoverage(fuzzHeights(FUZZ.mohair), 1, 3));
    expect(tex.generateMipmaps).toBe(true);
    expect(tex.minFilter).not.toBe(tex.magFilter); // a mipmap filter, not nearest
  });

  it("pushes each shell out along the normal on the GPU, fades by coverage and tints the sheen", () => {
    const look = FUZZ.mohair;
    const m = shellMaterial(look, look.shells, 0.6, shellTexture(new Uint8Array(512 * 512)));
    // the anchors must exist in three's physical shader, or the injection would silently do nothing
    const shader = { uniforms: {}, vertexShader: ShaderLib.physical.vertexShader, fragmentShader: ShaderLib.physical.fragmentShader };
    m.onBeforeCompile(shader as never, undefined as never);
    expect(shader.vertexShader).toContain("transformed += normal * fuzzOffset;");
    expect(shader.fragmentShader).toContain("diffuseColor.a *= fuzzA;");
    expect(shader.fragmentShader).toContain("material.sheenColor *= vColor.rgb;");
    expect(shader.fragmentShader).not.toContain("#include <alphatest_fragment>");
    const u = shader.uniforms as Record<string, { value: number }>;
    expect(u.fuzzOffset.value).toBeCloseTo(look.height * 0.6, 6);
    expect(m.depthWrite).toBe(false);
  });
});

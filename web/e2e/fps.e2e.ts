import { expect, test, type Page } from "@playwright/test";
import { BIG, type Hook, startApp } from "./helpers";

/**
 * A9 viewer: ≥ 30 FPS at ≈ 5 000 stitches, overview and close-up. Only valid on a hardware GPU: runs on macOS
 * with Metal (SwiftShader on CI says nothing about the viewer) and is skipped elsewhere. The frame-rate limit is
 * lifted, so the numbers show the headroom above the display's 60/120 Hz.
 */
test.skip(process.platform !== "darwin", "FPS needs the hardware GPU of a Mac");
test.use({
  viewport: { width: 1440, height: 900 },
  deviceScaleFactor: 2, // a MacBook display
  launchOptions: { args: ["--use-angle=metal", "--disable-gpu-vsync", "--disable-frame-rate-limit"] },
});
test.setTimeout(240_000);

const MIN_FPS = 30;
const hook = (page: Page) => page.evaluateHandle(() => (window as unknown as { __stitchcraft: Hook }).__stitchcraft);

/** Frames per second over `seconds` one-second windows; returns them and their median. */
async function measure(page: Page, seconds = 5): Promise<{ fps: number[]; median: number }> {
  const fps = await page.evaluate(
    (n) =>
      new Promise<number[]>((resolve) => {
        const out: number[] = [];
        let frames = 0;
        let start = 0;
        const tick = (t: number) => {
          if (!start) start = t;
          else frames++;
          if (t - start >= 1000) {
            out.push((frames * 1000) / (t - start));
            frames = 0;
            start = t;
          }
          if (out.length < n) requestAnimationFrame(tick);
          else resolve(out);
        };
        requestAnimationFrame(tick);
      }),
    seconds,
  );
  const sorted = [...fps].sort((a, b) => a - b);
  return { fps, median: sorted[Math.floor(sorted.length / 2)] };
}

for (const material of ["cotton", "mohair"] as const) {
  test(`A9 Viewer: ≥ ${MIN_FPS} FPS bei ≈ 5 000 Maschen, Totale und Nahaufnahme (${material})`, async ({ page }) => {
    await startApp(page);
    const renderer = await page.evaluate(() => {
      const gl = document.createElement("canvas").getContext("webgl2")!;
      return gl.getParameter(gl.getExtension("WEBGL_debug_renderer_info")!.UNMASKED_RENDERER_WEBGL) as string;
    });
    test.skip(/swiftshader/i.test(renderer), `no hardware GPU: ${renderer}`);
    await page.evaluate(([text, m]) => {
      localStorage.setItem("stitchcraft.text", JSON.stringify(text));
      const params = JSON.parse(localStorage.getItem("stitchcraft.params") ?? "{}");
      localStorage.setItem("stitchcraft.params", JSON.stringify({ ...params, material: m }));
    }, [BIG.join("\n"), material] as const);
    await page.reload();
    await page.getByRole("button", { name: "3D-Vorschau" }).click();
    await expect(page.locator(".stats")).toContainText("4896 Maschen", { timeout: 180_000 });
    await page.waitForTimeout(2000); // first frames build the tubes

    const wide = await measure(page);
    const wideLevels = await (await hook(page)).evaluate((h) => h.levels());
    expect(await (await hook(page)).evaluate((h) => h.closeUp(30))).toBe(true);
    await page.waitForTimeout(2000);
    const close = await measure(page);
    const closeLevels = await (await hook(page)).evaluate((h) => h.levels());

    const report = { renderer, material, wide, close, wideLevels, closeLevels };
    test.info().annotations.push({ type: "A9 FPS", description: JSON.stringify(report) });
    console.log(`A9 FPS ${JSON.stringify(report)}`);
    // the overview draws coarse tubes without fuzz, the close-up full tubes with fuzz around the camera
    expect(wideLevels.chunks[0] + wideLevels.chunks[1]).toBeLessThan(wideLevels.chunks.at(-1)!);
    expect(closeLevels.chunks[0]).toBeGreaterThan(0);
    if (material === "mohair") expect(closeLevels.fuzz).toBeGreaterThan(0);
    expect(wide.median).toBeGreaterThanOrEqual(MIN_FPS);
    expect(close.median).toBeGreaterThanOrEqual(MIN_FPS);
  });
}

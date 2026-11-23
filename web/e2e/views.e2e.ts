import { expect, test } from "@playwright/test";
import { runPreview, SPHERE, startApp, typePattern } from "./helpers";

// Baselines are platform specific (SwiftShader output differs per OS); CI (Linux) has none, so these run locally on macOS only.
test.skip(process.platform !== "darwin" && !process.env.UPDATE_LINUX, "Screenshot baselines exist for macOS only");

for (const [view, label] of [["front", "vorne"], ["side", "seitlich"], ["top", "oben"], ["iso", "iso"]] as const) {
  test(`Kamera-Preset ${view}`, async ({ page }) => {
    await startApp(page);
    await typePattern(page, SPHERE);
    await runPreview(page);
    await page.getByRole("button", { name: label, exact: true }).click();
    await expect(page.getByRole("button", { name: label, exact: true })).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator("canvas")).toHaveScreenshot(`${view}.png`, {
      animations: "disabled",
      maxDiffPixelRatio: 0.02,
      threshold: 0.2,
    });
  });
}

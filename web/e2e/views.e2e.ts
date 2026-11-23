import { expect, test, type Page } from "@playwright/test";
import { ASYMMETRIC, type Hook, runPreview, startApp, typePattern } from "./helpers";

// Baselines are platform specific (SwiftShader output differs per OS); CI (Linux) has none, so these run locally on macOS only.
test.skip(process.platform !== "darwin" && !process.env.UPDATE_LINUX, "Screenshot baselines exist for macOS only");

const VIEWS = [["front", "vorne"], ["side", "seitlich"], ["top", "oben"], ["iso", "iso"]] as const;
type ViewId = (typeof VIEWS)[number][0];
// camera direction per preset for flat pieces (Viewer.viewDirection), normalised
const DIRECTION: Record<ViewId, [number, number, number]> = {
  front: [0, 0, 1],
  side: [1, 0, 0.001],
  top: [0, 1, 0.001],
  iso: [0.8, -0.8, 1],
};
const SHOT = { animations: "disabled", maxDiffPixelRatio: 0.005, threshold: 0.2 } as const;

/** Runs `shoot` with the controls that float over the canvas hidden (the stats chip shows timings): the render only. */
async function renderOnly<T>(page: Page, shoot: () => Promise<T>): Promise<T> {
  const style = await page.addStyleTag({ content: ".info-chip, .viewer-actions, .dock { visibility: hidden !important; }" });
  try {
    return await shoot();
  } finally {
    await style.evaluate((el) => (el as Element).remove());
  }
}

async function select(page: Page, view: ViewId) {
  const label = VIEWS.find(([v]) => v === view)![1];
  const button = page.getByRole("button", { name: label, exact: true });
  await button.click();
  await expect(button).toHaveAttribute("aria-pressed", "true");
  const want = DIRECTION[view];
  const len = Math.hypot(...want);
  await expect
    .poll(() => page.evaluate(() => (window as unknown as { __stitchcraft: Hook }).__stitchcraft.cameraDirection()))
    .toEqual(want.map((c) => expect.closeTo(c / len, 3)));
}

async function prepare(page: Page) {
  await startApp(page);
  await typePattern(page, ASYMMETRIC);
  await runPreview(page);
}

for (const [view] of VIEWS) {
  test(`Kamera-Preset ${view}`, async ({ page }) => {
    await prepare(page);
    await select(page, view);
    await renderOnly(page, () => expect(page.locator("canvas")).toHaveScreenshot(`${view}.png`, SHOT));
  });
}

test("Kamera-Presets unterscheiden sich deutlich voneinander", async ({ page }) => {
  await prepare(page);
  // each preset's render must differ from every other baseline by more than three times the tolerance
  for (const [view] of VIEWS) {
    await select(page, view);
    await page.waitForTimeout(500);
    const shot = await renderOnly(page, () => page.locator("canvas").screenshot({ animations: "disabled" }));
    for (const [other] of VIEWS) {
      if (other === view) continue;
      expect(shot, `${view} vs ${other}`).not.toMatchSnapshot(`${other}.png`, { maxDiffPixelRatio: 0.015, threshold: SHOT.threshold });
    }
  }
});

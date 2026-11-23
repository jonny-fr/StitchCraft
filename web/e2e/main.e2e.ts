import { expect, test } from "@playwright/test";
import { SPHERE, startApp, typePattern } from "./helpers";

test("Beispiel tippen, Lint, Vorschau, Klick auf Masche markiert Token", async ({ page }) => {
  await startApp(page);
  const wrong = [...SPHERE];
  wrong[1] = "Rd. 2: 6x zun (13)";
  await typePattern(page, wrong);

  // count gutter and the diagnostic for the wrong control number
  await expect(page.locator(".cm-counts .bad")).toHaveCount(1);
  await expect(page.locator("ul.diagnostics")).toContainText("12 Maschen gezählt, angegeben sind 13");
  await expect(page.getByRole("button", { name: "3D-Vorschau" })).toBeEnabled();

  // fix it
  await typePattern(page, SPHERE);
  await expect(page.locator("ul.diagnostics")).not.toContainText("Maschen gezählt");
  await expect(page.locator(".cm-counts .bad")).toHaveCount(0);
  await expect(page.locator(".cm-counts")).toContainText("36");

  await page.getByRole("button", { name: "3D-Vorschau" }).click();
  await expect(page.locator("progress")).toBeVisible();
  await expect(page.locator("canvas")).toBeVisible({ timeout: 60_000 });
  await expect(page.locator(".stats")).toContainText("Maschen");

  // click a stitch in the canvas
  await page.waitForFunction(() => Boolean((window as unknown as { __stitchcraft?: unknown }).__stitchcraft));
  const hit = await page.evaluate(() => (window as unknown as { __stitchcraft: { hitPoint(): { x: number; y: number } | null } }).__stitchcraft.hitPoint());
  expect(hit).not.toBeNull();
  await page.mouse.click(hit!.x, hit!.y);

  await expect(page.getByText(/^Masche \d+ \(/)).toBeVisible();
  const selection = await page.evaluate(() => getSelection()?.toString() ?? "");
  expect(selection.trim().length).toBeGreaterThan(0);
  expect(SPHERE.join("\n")).toContain(selection);
});

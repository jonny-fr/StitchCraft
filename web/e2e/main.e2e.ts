import { expect, test } from "@playwright/test";
import { closePopover, openPopover, openYarn, runPreview, SPHERE, type Hook, startApp, typePattern } from "./helpers";

test("Beispiel tippen, Lint, Vorschau, Klick auf Masche markiert Token", async ({ page }) => {
  await startApp(page);
  const wrong = [...SPHERE];
  wrong[1] = "Rd. 2: 6x zun (13)";
  await typePattern(page, wrong);

  // count gutter, the status line and, unfolded, the diagnostic for the wrong control number
  await expect(page.locator(".cm-counts .bad")).toHaveCount(1);
  const status = page.locator(".status-bar");
  await expect(status).toHaveText(/^1 Fehler/);
  await status.click();
  await expect(page.locator("ul.diagnostics")).toBeVisible();
  await expect(page.locator("ul.diagnostics")).toContainText("12 Maschen gezählt, angegeben sind 13");
  await expect(page.locator("table.counts tr.bad")).toHaveCount(1);
  await expect(page.getByRole("button", { name: "3D-Vorschau" })).toBeEnabled();

  // fix it
  await typePattern(page, SPHERE);
  await expect(status).toHaveText(/^Keine Probleme/);
  await expect(page.locator("ul.diagnostics")).not.toContainText("Maschen gezählt");
  await expect(page.locator(".cm-counts .bad")).toHaveCount(0);
  await expect(page.locator(".cm-counts")).toContainText("36");

  await page.getByRole("button", { name: "3D-Vorschau" }).click();
  await expect(page.locator("progress")).toBeVisible();
  await expect(page.locator("canvas")).toBeVisible({ timeout: 60_000 });
  await expect(page.locator(".stats")).toContainText("Maschen");

  // click a stitch in the canvas
  await page.waitForFunction(() => Boolean((window as unknown as { __stitchcraft?: unknown }).__stitchcraft));
  const hit = await page.evaluate(() => (window as unknown as { __stitchcraft: Hook }).__stitchcraft.hitPoint());
  expect(hit).not.toBeNull();

  // the span of the stitch under the cursor, from the server's shape
  await openPopover(page, page.getByRole("button", { name: "Export", exact: true }));
  const id = (await page.getByRole("link", { name: "GLB exportieren" }).getAttribute("href"))!.split("/")[4];
  await closePopover(page);
  const shape = await (await page.request.get(`/api/v1/previews/${id}/shape.json`)).json();
  const stitch = shape.stitches.find((s: { id: number }) => s.id === hit!.stitch);
  expect(stitch.span).not.toBeNull();
  const expected = SPHERE.join("\n").slice(stitch.span.start, stitch.span.end);
  expect(expected.length).toBeGreaterThan(0);

  await page.mouse.click(hit!.x, hit!.y);

  await expect(page.getByText(`Masche ${hit!.stitch} (`)).toBeVisible();
  expect(await page.evaluate(() => getSelection()?.toString() ?? "")).toBe(expected);
});

test("Faserflaum bei Mohair: Schalter blendet die Fasern aus und wieder ein, das Bild ist danach pixelgleich", async ({ page }) => {
  await startApp(page);
  const yarn = await openYarn(page);
  await yarn.getByLabel("Material").selectOption("mohair");
  await closePopover(page);
  await runPreview(page);
  // the canvas pixels alone (the controls floating over it keep a focus ring after the popover closed)
  const pixels = () => page.evaluate(() => document.querySelector("canvas")!.toDataURL("image/png"));
  const hook = () => page.evaluate(() => (window as unknown as { __stitchcraft: Hook }).__stitchcraft.levels());
  await expect.poll(async () => (await hook()).fuzz).toBeGreaterThan(0);
  await page.waitForTimeout(2000); // SwiftShader takes a while per frame
  const withFuzz = await pixels();

  const toggle = async () => {
    await openPopover(page, page.getByRole("button", { name: "Werkzeuge" }));
    await page.getByLabel("Faserflaum").click();
    await closePopover(page);
  };
  await toggle();
  expect((await hook()).fuzz).toBe(0);
  await expect.poll(pixels).not.toBe(withFuzz);
  await toggle();
  await expect.poll(pixels).toBe(withFuzz);
});

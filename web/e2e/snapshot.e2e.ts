import { expect, test, type Page } from "@playwright/test";
import { ASYMMETRIC, createPreview, SPHERE } from "./helpers";

const status = (page: Page) => page.evaluate(() => (window as unknown as { __stitchcraftSnapshot?: string }).__stitchcraftSnapshot);

async function snapshot(page: Page, query: string): Promise<Buffer> {
  await page.goto(`/?${query}`);
  await expect.poll(() => status(page), { timeout: 60_000 }).toBe("ready");
  return page.screenshot();
}

/** Decodes both PNGs in the page and returns the share of pixels that differ clearly. */
async function diffRatio(page: Page, a: Buffer, b: Buffer): Promise<number> {
  return page.evaluate(async ([x, y]) => {
    const px = async (png: string) => {
      const bmp = await createImageBitmap(await (await fetch(`data:image/png;base64,${png}`)).blob());
      const ctx = new OffscreenCanvas(bmp.width, bmp.height).getContext("2d")!;
      ctx.drawImage(bmp, 0, 0);
      return ctx.getImageData(0, 0, bmp.width, bmp.height).data;
    };
    const [p, q] = [await px(x), await px(y)];
    let n = 0;
    for (let i = 0; i < p.length; i += 4) if (Math.abs(p[i] - q[i]) + Math.abs(p[i + 1] - q[i + 1]) + Math.abs(p[i + 2] - q[i + 2]) > 40) n++;
    return n / (p.length / 4);
  }, [a.toString("base64"), b.toString("base64")]);
}

async function distinctColours(page: Page, png: Buffer): Promise<number> {
  return page.evaluate(async (data) => {
    const bmp = await createImageBitmap(await (await fetch(`data:image/png;base64,${data}`)).blob());
    const ctx = new OffscreenCanvas(bmp.width, bmp.height).getContext("2d")!;
    ctx.drawImage(bmp, 0, 0);
    const d = ctx.getImageData(0, 0, bmp.width, bmp.height).data;
    const seen = new Set<number>();
    for (let i = 0; i < d.length; i += 4 * 97) seen.add((d[i] << 16) | (d[i + 1] << 8) | d[i + 2]);
    return seen.size;
  }, png.toString("base64"));
}

test("Snapshot-Modus zeigt nur das Garn und meldet Bereitschaft", async ({ page }) => {
  const id = await createPreview(page, SPHERE);
  const shot = await snapshot(page, `snapshot=${id}&view=front&color=c0392b&material=cotton`);
  await expect(page.locator("canvas")).toBeVisible();
  await expect(page.locator("[data-snapshot]")).toHaveAttribute("data-snapshot", "ready");
  // no editor, buttons or inputs: the page is canvas only
  await expect(page.locator("button, input, textarea, .cm-content, header")).toHaveCount(0);

  // the render is neither empty nor a single colour
  expect(await distinctColours(page, shot)).toBeGreaterThan(50);
});

test("Snapshot-Ansichten und Farben unterscheiden sich", async ({ page }) => {
  const id = await createPreview(page, ASYMMETRIC);
  const front = await snapshot(page, `snapshot=${id}&view=front`);
  const top = await snapshot(page, `snapshot=${id}&view=top`);
  const red = await snapshot(page, `snapshot=${id}&view=front&color=c0392b`);
  expect(await diffRatio(page, front, top)).toBeGreaterThan(0.05);
  expect(await diffRatio(page, front, red)).toBeGreaterThan(0.05);
});

test("Unbekannter Schlüssel und ungültige Parameter melden error", async ({ page }) => {
  for (const q of ["snapshot=doesnotexist1", "snapshot=abc&view=bottom"]) {
    await page.goto(`/?${q}`);
    await expect.poll(() => status(page), { timeout: 20_000 }).toBe("error");
    await expect(page.locator("canvas")).toHaveCount(0);
  }
});

test("Zwei Snapshots derselben Eingabe sind pixelgleich, mit Ply-Normal-Map und Faserflaum", async ({ page }) => {
  const id = await createPreview(page, SPHERE);
  const query = `snapshot=${id}&view=iso&color=c0392b&material=mohair`;
  const first = await snapshot(page, query);
  const second = await snapshot(page, query);
  expect(second.equals(first)).toBe(true);
  // and the fuzz is really drawn: mohair differs from acrylic (no fuzz)
  const acrylic = await snapshot(page, `snapshot=${id}&view=iso&color=c0392b&material=acrylic`);
  expect(await diffRatio(page, first, acrylic)).toBeGreaterThan(0.01);
});

import { expect, type Page } from "@playwright/test";

export const SPHERE = [
  "Rd. 1: 6 fM in MR (6)",
  "Rd. 2: 6x zun (12)",
  "Rd. 3: (1 fM, zun) x6 (18)",
  "Rd. 4: (1 fM, zun, 1 fM) x6 (24)",
  "Rd. 5: (3 fM, zun) x6 (30)",
  "Rd. 6: (2 fM, zun, 2 fM) x6 (36)",
  "Rd. 7-12: 36 fM (36)",
  "Rd. 13: (2 fM, abn, 2 fM) x6 (30)",
  "Rd. 14: (3 fM, abn) x6 (24)",
  "Rd. 15: (1 fM, abn, 1 fM) x6 (18)",
  "Füllen",
  "Rd. 16: (1 fM, abn) x6 (12)",
  "Rd. 17: 6x abn (6)",
  "Faden abschneiden",
];

export const editor = (page: Page) => page.locator(".cm-content");

/** Replaces the editor content line by line, like a person typing. */
export async function typePattern(page: Page, lines: string[]) {
  const ed = editor(page);
  await ed.click();
  await page.keyboard.press("ControlOrMeta+a");
  await page.keyboard.press("Delete");
  for (const [i, line] of lines.entries()) {
    if (i) await page.keyboard.press("Enter");
    await page.keyboard.insertText(line);
  }
  expect(await editorText(page)).toBe(lines.join("\n"));
}

export async function editorText(page: Page): Promise<string> {
  return page.evaluate(() => [...document.querySelectorAll(".cm-line")].map((l) => l.textContent).join("\n"));
}

export async function startApp(page: Page, query = "?e2e") {
  await page.goto(`/${query}`);
  await page.evaluate(() => localStorage.clear());
  await page.goto(`/${query}`);
  await expect(editor(page)).toBeVisible();
}

/** Runs the preview and waits until the 3D canvas shows the result. */
export async function runPreview(page: Page) {
  await page.getByRole("button", { name: "3D-Vorschau" }).click();
  await expect(page.locator("canvas")).toBeVisible({ timeout: 60_000 });
  await page.waitForFunction(() => Boolean((window as unknown as { __stitchcraft?: unknown }).__stitchcraft));
}

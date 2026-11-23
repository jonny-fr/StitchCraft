import { expect, type Locator, type Page } from "@playwright/test";

const API = "http://localhost:8766"; // playwright.config.ts API_PORT

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

/** Flat piece that widens on one side only: front, side, top and iso all look clearly different. */
export const ASYMMETRIC = [
  "R 1: 11 Lm, wenden",
  "R 2: 10 fM, 1 Lm, wenden (10)",
  "R 3: 9 fM, zun, 1 Lm, wenden (11)",
  "R 4: 10 fM, zun, 1 Lm, wenden (12)",
  "R 5: 5 fM, 7 hStb, 1 Lm, wenden (12)",
  "R 6: 11 fM, zun, 1 Lm, wenden (13)",
  "R 7: 6 fM, 7 Stb (13)",
];

export interface Hook {
  hitPoint(): { x: number; y: number; stitch: number } | null;
  cameraDirection(): [number, number, number];
}

/** Computes a preview straight through the API and waits until it is cached; returns its key. */
export async function createPreview(page: Page, lines: string[]): Promise<string> {
  const res = await page.request.post(`${API}/api/v1/previews`, { data: { text: lines.join("\n"), dialect: "de", params: {} } });
  const { id } = await res.json();
  await expect.poll(async () => (await page.request.get(`${API}/api/v1/previews/${id}/shape.json`)).status(), { timeout: 60_000 }).toBe(200);
  return id;
}

/** A segment of the context pill ("Dialekt", "Garn", "Farben"); its name is the title plus the current value. */
export const segment = (page: Page, title: string) => page.getByRole("button", { name: new RegExp(`^${title}(\\s|$)`) });

export const menuButton = (page: Page) => page.getByRole("button", { name: /^(Menü|Menu)$/ });

/** Clicks a popover trigger and returns the panel it opened. */
export async function openPopover(page: Page, trigger: Locator): Promise<Locator> {
  await trigger.click();
  await expect(trigger).toHaveAttribute("aria-expanded", "true");
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  return dialog;
}

/** Opens the yarn popover with all fields shown. */
export async function openYarn(page: Page): Promise<Locator> {
  const dialog = await openPopover(page, segment(page, "Garn"));
  const more = dialog.getByRole("button", { name: "Mehr" });
  if ((await more.getAttribute("aria-expanded")) !== "true") await more.click();
  return dialog;
}

export async function closePopover(page: Page) {
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
}

/** Picks a .stitch.json through the menu's import entry, like a person in the file dialog. */
export async function importStitchFile(page: Page, file: string | { name: string; mimeType: string; buffer: Buffer }) {
  await openPopover(page, menuButton(page));
  const [chooser] = await Promise.all([page.waitForEvent("filechooser"), page.locator("label", { hasText: "Importieren" }).click()]);
  await chooser.setFiles(file);
}

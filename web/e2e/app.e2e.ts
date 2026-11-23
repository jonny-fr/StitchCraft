import { expect, test, type Page } from "@playwright/test";
import { closePopover, editor, editorText, importStitchFile, menuButton, openPopover, openYarn, segment, SPHERE, startApp, typePattern } from "./helpers";

const material = (page: Page) => page.locator("label").filter({ hasText: /^Material/ }).locator("select");
const AMBIGUOUS = ["R1: 6 dc in MR (6)"];

async function setDialect(page: Page, title: string, label: string, value: string) {
  await openPopover(page, segment(page, title));
  await page.getByLabel(label).selectOption(value);
  await closePopover(page);
}

async function setLanguage(page: Page, label: string, value: string) {
  await openPopover(page, menuButton(page));
  await page.getByLabel(label).selectOption(value);
  await closePopover(page);
}

async function expectDialect(page: Page, title: string, label: string, value: string) {
  await openPopover(page, segment(page, title));
  await expect(page.getByLabel(label)).toHaveValue(value);
  await closePopover(page);
}

test("UI-Sprache wechselt Texte, nicht den Anleitungs-Dialekt", async ({ page }) => {
  await startApp(page);
  await setDialect(page, "Dialekt", "Anleitungs-Dialekt", "en-UK");
  await setLanguage(page, "Sprache", "en");
  await expect(page.getByRole("button", { name: "3D preview" })).toBeVisible();
  await expectDialect(page, "Terms", "Pattern terms", "en-UK");
  await setLanguage(page, "Language", "de");
  await expect(page.getByRole("button", { name: "3D-Vorschau" })).toBeVisible();
  await expectDialect(page, "Dialekt", "Anleitungs-Dialekt", "en-UK");
});

test("Dialekt auto fragt bei mehrdeutigem Text nach", async ({ page }) => {
  await startApp(page);
  await setDialect(page, "Dialekt", "Anleitungs-Dialekt", "auto");
  await typePattern(page, AMBIGUOUS);
  await expect(page.getByText("US- oder UK-Begriffe?")).toBeVisible();
  await expect(segment(page, "Dialekt")).toHaveAccessibleName(/^Dialekt auto → en-(US|UK)$/);
  await page.getByRole("button", { name: "English (UK)" }).click();
  await expect(segment(page, "Dialekt")).toHaveAccessibleName("Dialekt English (UK)");
  await expectDialect(page, "Dialekt", "Anleitungs-Dialekt", "en-UK");
  await expect(page.getByText("US- oder UK-Begriffe?")).toBeHidden();
});

test("Export und Import stellen Text und Parameter wieder her; kaputte Datei lässt den Text unverändert", async ({ page }) => {
  await startApp(page);
  await typePattern(page, SPHERE);
  await openYarn(page);
  await page.getByLabel("Garnstärke (mm)").fill("3");
  await material(page).selectOption("mohair");
  await closePopover(page);

  await openPopover(page, menuButton(page));
  const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: /Exportieren/ }).click()]);
  expect(download.suggestedFilename()).toMatch(/\.stitch\.json$/);
  const path = await download.path();

  await typePattern(page, ["Rd. 1: 6 fM in MR (6)"]);
  await openYarn(page);
  await page.getByLabel("Garnstärke (mm)").fill("2");
  await material(page).selectOption("cotton");
  await closePopover(page);

  await importStitchFile(page, path);
  await expect.poll(() => editorText(page)).toBe(SPHERE.join("\n"));
  await openYarn(page);
  await expect(page.getByLabel("Garnstärke (mm)")).toHaveValue("3");
  await expect(material(page)).toHaveValue("mohair");
  await closePopover(page);

  await importStitchFile(page, { name: "kaputt.stitch.json", mimeType: "application/json", buffer: Buffer.from("{nope") });
  await expect(page.getByText("Datei ist kein gültiges JSON.")).toBeVisible();
  expect(await editorText(page)).toBe(SPHERE.join("\n"));
});

test("Mobil: Tabs wechseln zwischen Editor und 3D; Desktop: Split-Trenner", async ({ page }) => {
  await startApp(page);
  await expect(page.getByRole("separator")).toBeVisible();
  await expect(page.getByRole("button", { name: "Anleitung", exact: true })).toBeHidden();

  await page.setViewportSize({ width: 390, height: 844 });
  const editorTab = page.getByRole("button", { name: "Anleitung", exact: true });
  const viewerTab = page.getByRole("button", { name: "3D", exact: true });
  await expect(editorTab).toBeVisible();
  await expect(page.getByRole("separator")).toHaveCount(0);
  await expect(editor(page)).toBeVisible();
  await viewerTab.click();
  await expect(editor(page)).toBeHidden();
  await expect(page.locator("section.viewer")).toBeVisible();
  await editorTab.click();
  await expect(editor(page)).toBeVisible();
});

test("Wechsel über 768 px behält den Editor samt Verlauf", async ({ page }) => {
  await startApp(page);
  await typePattern(page, SPHERE.slice(0, 2));
  const node = await editor(page).elementHandle();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(editor(page)).toBeVisible();
  await page.setViewportSize({ width: 1280, height: 800 });
  expect(await node!.evaluate((el) => el.isConnected)).toBe(true);
  // undo history survived: undoing removes what was typed last
  await editor(page).click();
  await page.keyboard.press("ControlOrMeta+z");
  await expect.poll(() => editorText(page)).not.toBe(SPHERE.slice(0, 2).join("\n"));
});

test("Text und Parameter überleben ein Neuladen", async ({ page }) => {
  await startApp(page);
  await typePattern(page, SPHERE.slice(0, 3));
  await openYarn(page);
  await page.getByLabel("Garnstärke (mm)").fill("4");
  await closePopover(page);
  await setDialect(page, "Dialekt", "Anleitungs-Dialekt", "en-US");
  await page.reload();
  await expect.poll(() => editorText(page)).toBe(SPHERE.slice(0, 3).join("\n"));
  await openYarn(page);
  await expect(page.getByLabel("Garnstärke (mm)")).toHaveValue("4");
  await closePopover(page);
  await expectDialect(page, "Dialekt", "Anleitungs-Dialekt", "en-US");
});

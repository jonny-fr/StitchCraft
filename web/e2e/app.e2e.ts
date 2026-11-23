import { expect, test, type Page } from "@playwright/test";
import { editor, editorText, SPHERE, startApp, typePattern } from "./helpers";

const material = (page: Page) => page.locator("label").filter({ hasText: /^Material/ }).locator("select");
const AMBIGUOUS = ["R1: 6 dc in MR (6)"];

test("UI-Sprache wechselt Texte, nicht den Anleitungs-Dialekt", async ({ page }) => {
  await startApp(page);
  const dialect = page.getByLabel("Anleitungs-Dialekt");
  await dialect.selectOption("en-UK");
  await page.getByLabel("Sprache").selectOption("en");
  await expect(page.getByRole("button", { name: "3D preview" })).toBeVisible();
  await expect(page.getByLabel("Pattern terms")).toHaveValue("en-UK");
  await page.getByLabel("Language").selectOption("de");
  await expect(page.getByRole("button", { name: "3D-Vorschau" })).toBeVisible();
  await expect(page.getByLabel("Anleitungs-Dialekt")).toHaveValue("en-UK");
});

test("Dialekt auto fragt bei mehrdeutigem Text nach", async ({ page }) => {
  await startApp(page);
  await page.getByLabel("Anleitungs-Dialekt").selectOption("auto");
  await typePattern(page, AMBIGUOUS);
  await expect(page.getByText("US- oder UK-Begriffe?")).toBeVisible();
  await page.getByRole("button", { name: "English (UK)" }).click();
  await expect(page.getByLabel("Anleitungs-Dialekt")).toHaveValue("en-UK");
  await expect(page.getByText("US- oder UK-Begriffe?")).toBeHidden();
});

test("Export und Import stellen Text und Parameter wieder her; kaputte Datei lässt den Text unverändert", async ({ page }) => {
  await startApp(page);
  await typePattern(page, SPHERE);
  await page.getByLabel("Garnstärke (mm)").fill("3");
  await material(page).selectOption("mohair");

  const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: /Exportieren/ }).click()]);
  expect(download.suggestedFilename()).toMatch(/\.stitch\.json$/);
  const path = await download.path();

  await typePattern(page, ["Rd. 1: 6 fM in MR (6)"]);
  await page.getByLabel("Garnstärke (mm)").fill("2");
  await material(page).selectOption("cotton");

  await page.locator('input[type="file"][accept*="json"]').setInputFiles(path);
  await expect.poll(() => editorText(page)).toBe(SPHERE.join("\n"));
  await expect(page.getByLabel("Garnstärke (mm)")).toHaveValue("3");
  await expect(material(page)).toHaveValue("mohair");

  await page.locator('input[type="file"][accept*="json"]').setInputFiles({ name: "kaputt.stitch.json", mimeType: "application/json", buffer: Buffer.from("{nope") });
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

test("Text und Parameter überleben ein Neuladen", async ({ page }) => {
  await startApp(page);
  await typePattern(page, SPHERE.slice(0, 3));
  await page.getByLabel("Garnstärke (mm)").fill("4");
  await page.getByLabel("Anleitungs-Dialekt").selectOption("en-US");
  await page.reload();
  await expect.poll(() => editorText(page)).toBe(SPHERE.slice(0, 3).join("\n"));
  await expect(page.getByLabel("Garnstärke (mm)")).toHaveValue("4");
  await expect(page.getByLabel("Anleitungs-Dialekt")).toHaveValue("en-US");
});

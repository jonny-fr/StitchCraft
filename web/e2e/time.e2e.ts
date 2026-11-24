import { expect, test, type Page } from "@playwright/test";
import { closePopover, editor, openPopover, runPreview, SPHERE, startApp, timeChip, typePattern } from "./helpers";

const API = "http://localhost:8766"; // playwright.config.ts API_PORT

/** H4: the time chip shows the estimate live while typing, follows the pace and keeps an own pace. */
test.describe("H4 Häkelzeit", () => {
  test("Chip unten rechts im Platzhalter, aktualisiert sich beim Tippen ohne Vorschau", async ({ page }) => {
    await startApp(page);
    const previews: string[] = [];
    page.on("request", (r) => void (r.url().includes("/previews") && previews.push(r.url())));
    await typePattern(page, SPHERE);
    // H2: the same numbers as the API (and MCP, see services/mcp tests) for the same pattern
    const api = await (await page.request.post(`${API}/api/v1/validate`, { data: { text: SPHERE.join("\n"), dialect: "de" } })).json();
    expect([api.time_estimate.seconds_low, api.time_estimate.seconds_high]).toEqual([980, 1632]);
    await expect(timeChip(page)).toHaveText("Häkelzeit ≈ 15–25 min");
    await expect(timeChip(page)).toHaveAttribute("title", /ohne Ausstopfen, Zusammennähen und Fäden vernähen/);

    const chip = (await timeChip(page).boundingBox())!;
    const card = (await page.locator(".viewer-card").boundingBox())!;
    expect(card.x + card.width - (chip.x + chip.width)).toBeLessThanOrEqual(24);
    expect(card.y + card.height - (chip.y + chip.height)).toBeLessThanOrEqual(24);
    await expect(page.locator(".placeholder")).toBeVisible();

    await typePattern(page, [...SPHERE.slice(0, 7), "Rd. 7-30: 36 fM (36)"]);
    await expect(timeChip(page)).toHaveText(/≈ \d½?–\d½? h|≈ \d+–\d+ min/);
    await expect(timeChip(page)).not.toHaveText("Häkelzeit ≈ 15–25 min");
    await expect(page.locator("canvas")).toHaveCount(0);
    expect(previews).toEqual([]);
  });

  test("Tempo ändert die Zahl, das eigene Tempo wird gespeichert", async ({ page }) => {
    await startApp(page);
    await typePattern(page, SPHERE);
    await expect(timeChip(page)).toHaveText(/15–25 min/);

    const panel = await openPopover(page, timeChip(page));
    await expect(panel.getByRole("button", { name: "Geübt" })).toHaveAttribute("aria-pressed", "true");
    await expect(panel.getByRole("region", { name: "Nach Runden/Reihen" })).toContainText("Rd./R. 17");
    await panel.getByRole("button", { name: "Anfänger" }).click();
    await expect(timeChip(page)).toHaveText(/30–50 min/);
    await panel.getByRole("button", { name: "Schnell" }).click();
    await expect(timeChip(page)).toHaveText(/10–20 min/);

    // own pace: 12 sc per minute is half the table's practised pace, so twice the time
    await panel.getByLabel("Eigenes Tempo").fill("12");
    await expect(timeChip(page)).toHaveText(/35–55 min/);
    await expect(panel.getByRole("button", { name: "Schnell" })).toHaveAttribute("aria-pressed", "false");
    await closePopover(page);
    const stored = await page.evaluate(() => JSON.parse(localStorage.getItem("stitchcraft.pace")!));
    expect(stored).toEqual({ pace: "schnell", stitchesPerMinute: 12 });

    await page.reload();
    await expect(editor(page)).toBeVisible();
    await expect(timeChip(page)).toHaveText(/35–55 min/);
    const again = await openPopover(page, timeChip(page));
    await expect(again.getByLabel("Eigenes Tempo")).toHaveValue("12");
  });

  test("der Reihen-Slider zeigt die Zeit bis hier", async ({ page }) => {
    await startApp(page);
    await typePattern(page, SPHERE);
    await runPreview(page);
    await expect(timeChip(page)).toBeVisible();
    const upTo = page.locator(".time-up-to");
    await expect(upTo).toHaveText(/^bis hier ≈ 20 min$/);
    await page.getByLabel(/^Zeigen bis Reihe/).fill("1");
    await expect(upTo).toHaveText("bis hier < 1 min");
    await page.getByLabel(/^Zeigen bis Reihe/).fill("8");
    await expect(upTo).toHaveText(/^bis hier ≈ \d+ min$/);
  });
});

test.describe("H4 Häkelzeit mobil", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  const inViewport = async (page: Page) => {
    const box = (await timeChip(page).boundingBox())!;
    expect(box.x).toBeGreaterThanOrEqual(0);
    expect(box.x + box.width).toBeLessThanOrEqual(375);
  };

  test("Chip in beiden Tabs sichtbar", async ({ page }) => {
    await startApp(page);
    await typePattern(page, SPHERE);
    await expect(timeChip(page)).toHaveText(/15–25 min/);
    await inViewport(page);
    await page.getByRole("button", { name: "3D", exact: true }).click();
    await expect(page.locator("canvas")).toBeVisible({ timeout: 60_000 });
    await expect(timeChip(page)).toHaveText(/15–25 min/);
    await inViewport(page);
    // the chip and the dock do not cover each other
    const chip = (await timeChip(page).boundingBox())!;
    const dock = (await page.locator(".dock").boundingBox())!;
    expect(chip.y + chip.height <= dock.y || dock.y + dock.height <= chip.y || chip.x >= dock.x + dock.width).toBe(true);
  });
});

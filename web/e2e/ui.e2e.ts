import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Locator, type Page } from "@playwright/test";
import { contrast } from "../src/contrast";
import {
  closePopover,
  createPreview,
  editor,
  editorText,
  type Hook,
  importStitchFile,
  menuButton,
  openPopover,
  runPreview,
  segment,
  SPHERE,
  startApp,
  timeChip,
  typePattern,
} from "./helpers";

// the WebGL canvas is transparent; the viewer background sits on react-three-fiber's wrapper two levels up
const canvasBackground = (page: Page) => page.locator("canvas").locator("xpath=../..");
const PNG_1PX = Buffer.from("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==", "base64");

async function startWithTheme(page: Page, theme: "dark" | "light", query = "?e2e") {
  await page.goto(`/${query}`);
  await page.evaluate((th) => (localStorage.clear(), localStorage.setItem("stitchcraft.theme", JSON.stringify(th))), theme);
  await page.goto(`/${query}`);
  await expect(editor(page)).toBeVisible();
  await expect(page.locator("html")).toHaveAttribute("data-theme", theme);
}

/** Interactive elements a person sees, outside the editor. */
function visibleControls(page: Page): Promise<number> {
  return page.evaluate(() => {
    const sel = "button, a[href], input, select, textarea, [role='button'], [role='separator'], [tabindex]:not([tabindex='-1'])";
    return [...document.querySelectorAll<HTMLElement>(sel)].filter((el) => {
      const r = el.getBoundingClientRect();
      return !el.closest(".pattern-editor") && el.checkVisibility({ visibilityProperty: true }) && r.width > 0 && r.height > 0;
    }).length;
  });
}

test.describe("U1 Übersicht", () => {
  const firstLoad = async (page: Page) => {
    await startApp(page);
    await expect(page.locator(".status-bar")).toHaveText(/Keine Probleme/);
    await expect(timeChip(page)).toBeVisible(); // the time chip counts too
    const n = await visibleControls(page);
    test.info().annotations.push({ type: "Bedienelemente", description: String(n) });
    expect(n).toBeLessThanOrEqual(8);
  };
  test("beim ersten Laden höchstens 8 sichtbare Bedienelemente außerhalb des Editors", async ({ page }) => firstLoad(page));
  test.describe("mobil", () => {
    test.use({ viewport: { width: 375, height: 812 } });
    test("auch bei 375 px höchstens 8", async ({ page }) => firstLoad(page));
  });
});

/**
 * U2: every function is reachable in at most two clicks from the first load (or from a fresh preview for the
 * viewer functions); each test then uses the function once.
 */
test.describe("U2 Erreichbarkeit", () => {
  let clicks = 0;
  const click = async (target: Locator) => (clicks++, await target.click());
  test.beforeEach(() => void (clicks = 0));
  test.afterEach(() => expect(clicks, "Klicks bis zur Funktion").toBeLessThanOrEqual(2));

  const yarn = (more: boolean) => async (page: Page) => {
    await click(segment(page, "Garn"));
    if (more) await click(page.getByRole("button", { name: "Mehr" }));
  };
  const PARAMS: [string, boolean, (field: Locator) => Promise<unknown>, string][] = [
    ["Garngewicht-Klasse", false, (f) => f.selectOption("bulky"), "bulky"],
    ["Material", false, (f) => f.selectOption("mohair"), "mohair"],
    ["Garnstärke (mm)", true, (f) => f.fill("3"), "3"],
    ["Nadelstärke (mm)", true, (f) => f.fill("4"), "4"],
    ["Maschenprobe: Maschen / 10 cm", true, (f) => f.fill("18"), "18"],
    ["Maschenprobe: Reihen / 10 cm", true, (f) => f.fill("20"), "20"],
    ["Füllung", true, (f) => f.fill("0.3"), "0.3"],
    ["Händigkeit", true, (f) => f.selectOption("left"), "left"],
    ["Außenseite", true, (f) => f.selectOption("wrong"), "wrong"],
  ];
  for (const [label, more, use, value] of PARAMS) {
    test(`Garnparameter ${label}`, async ({ page }) => {
      await startApp(page);
      await yarn(more)(page);
      const field = page.getByRole("dialog").getByLabel(label);
      await use(field);
      await expect(field).toHaveValue(value);
    });
  }

  test("Dialekt", async ({ page }) => {
    await startApp(page);
    await click(segment(page, "Dialekt"));
    await page.getByLabel("Anleitungs-Dialekt").selectOption("en-US");
    await expect(segment(page, "Dialekt")).toHaveAccessibleName("Dialekt English (US)");
  });

  test("Beispiel", async ({ page }) => {
    await startApp(page);
    await typePattern(page, ["Rd. 1: 6 fM in MR (6)"]);
    await click(menuButton(page));
    await page.getByLabel("Beispiel").selectOption("1-square");
    await expect.poll(() => editorText(page)).toContain("Lm");
  });

  test("Export", async ({ page }) => {
    await startApp(page);
    await click(menuButton(page));
    const [download] = await Promise.all([page.waitForEvent("download"), click(page.getByRole("button", { name: /Exportieren/ }))]);
    expect(download.suggestedFilename()).toMatch(/\.stitch\.json$/);
  });

  test("Import", async ({ page }) => {
    await startApp(page);
    await click(menuButton(page));
    const file = JSON.stringify({ format: "stitchcraft", version: 1, text: "Rd. 1: 6 fM in MR (6)", dialect: "de" });
    const [chooser] = await Promise.all([page.waitForEvent("filechooser"), click(page.locator("label", { hasText: "Importieren" }))]);
    await chooser.setFiles({ name: "a.stitch.json", mimeType: "application/json", buffer: Buffer.from(file) });
    await expect.poll(() => editorText(page)).toBe("Rd. 1: 6 fM in MR (6)");
  });

  test("Farbe", async ({ page }) => {
    await startApp(page);
    await click(segment(page, "Farben"));
    await page.getByLabel("Garnfarbe").fill("#3366cc");
    await expect(page.getByLabel("Garnfarbe")).toHaveValue("#3366cc");
  });

  test("UI-Sprache", async ({ page }) => {
    await startApp(page);
    await click(menuButton(page));
    await page.getByLabel("Sprache").selectOption("en");
    await expect(page.getByRole("button", { name: "3D preview" })).toBeVisible();
  });

  test("Tempo der Häkelzeit", async ({ page }) => {
    await startApp(page);
    const before = await timeChip(page).textContent();
    await click(timeChip(page));
    await click(page.getByRole("button", { name: "Anfänger" }));
    await expect(timeChip(page)).not.toHaveText(before!);
  });

  test("Eigenes Tempo", async ({ page }) => {
    await startApp(page);
    await click(timeChip(page));
    await page.getByLabel("Eigenes Tempo").fill("12");
    await expect.poll(() => page.evaluate(() => JSON.parse(localStorage.getItem("stitchcraft.pace")!).stitchesPerMinute)).toBe(12);
  });

  test("Theme", async ({ page }) => {
    await startApp(page);
    await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
    await click(menuButton(page));
    await page.getByLabel("Darstellung").selectOption("light");
    await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
    await page.getByLabel("Darstellung").selectOption("system");
    await expect(page.locator("html")).toHaveAttribute("data-theme", "system");
  });

  test.describe("im Viewer", () => {
    test.beforeEach(async ({ page }) => {
      await startApp(page);
      await runPreview(page);
      clicks = 0; // starting the preview is not part of the way to the function
    });

    test("Ansichten", async ({ page }) => {
      await click(page.getByRole("button", { name: "oben", exact: true }));
      await expect(page.getByRole("button", { name: "oben", exact: true })).toHaveAttribute("aria-pressed", "true");
    });

    test("Reihen-Slider", async ({ page }) => {
      const slider = page.getByLabel(/^Zeigen bis Reihe/);
      await slider.fill("5");
      await expect(page.getByText("Zeigen bis Reihe 5")).toBeVisible();
    });

    test("Foto-Overlay", async ({ page }) => {
      await click(page.getByRole("button", { name: "Werkzeuge" }));
      const [chooser] = await Promise.all([page.waitForEvent("filechooser"), click(page.locator("label", { hasText: "Foto-Overlay" }))]);
      await chooser.setFiles({ name: "foto.png", mimeType: "image/png", buffer: PNG_1PX });
      await expect(page.locator("img.overlay")).toBeVisible();
    });

    test("Deckkraft", async ({ page }) => {
      await click(page.getByRole("button", { name: "Werkzeuge" }));
      // the opacity belongs to a photo: choosing one is the second click
      const [chooser] = await Promise.all([page.waitForEvent("filechooser"), click(page.locator("label", { hasText: "Foto-Overlay" }))]);
      await chooser.setFiles({ name: "foto.png", mimeType: "image/png", buffer: PNG_1PX });
      await page.getByLabel("Deckkraft").fill("0.8");
      await expect(page.locator("img.overlay")).toHaveCSS("opacity", "0.8");
    });

    test("Silhouette", async ({ page }) => {
      await click(page.getByRole("button", { name: "Werkzeuge" }));
      await click(page.getByLabel("Silhouette"));
      await expect(canvasBackground(page)).toHaveCSS("background-color", "rgb(255, 255, 255)");
    });

    test("Faserflaum", async ({ page }) => {
      const levels = () => page.evaluate(() => (window as unknown as { __stitchcraft: Hook }).__stitchcraft.levels());
      expect((await levels()).fuzz).toBeGreaterThan(0); // cotton: a subtle fuzz shell
      await click(page.getByRole("button", { name: "Werkzeuge" }));
      await click(page.getByLabel("Faserflaum"));
      await expect(page.getByLabel("Faserflaum")).not.toBeChecked();
      await expect.poll(async () => (await levels()).fuzz).toBe(0);
    });

    test("PNG", async ({ page }) => {
      await click(page.getByRole("button", { name: "Export", exact: true }));
      const [download] = await Promise.all([page.waitForEvent("download"), click(page.getByRole("button", { name: "PNG speichern" }))]);
      expect(download.suggestedFilename()).toBe("stitchcraft-iso.png");
    });

    test("GLB", async ({ page }) => {
      await click(page.getByRole("button", { name: "Export", exact: true }));
      const link = page.getByRole("link", { name: "GLB exportieren" });
      await expect(link).toHaveAttribute("href", /\/model\.glb$/);
      expect((await page.request.get((await link.getAttribute("href"))!)).ok()).toBe(true);
    });
  });
});

test.describe("U3 Farbe", () => {
  const colorInputs = (page: Page) => page.locator('input[type="color"]');

  test("genau eine Farbeinstellung, vor und nach der Vorschau", async ({ page }) => {
    await startApp(page);
    for (const title of ["Dialekt", "Garn"]) {
      await openPopover(page, segment(page, title));
      if (title === "Garn") await page.getByRole("button", { name: "Mehr" }).click();
      await expect(colorInputs(page)).toHaveCount(0);
      await closePopover(page);
    }
    await openPopover(page, menuButton(page));
    await expect(colorInputs(page)).toHaveCount(0);
    await closePopover(page);
    await openPopover(page, segment(page, "Farben"));
    await expect(colorInputs(page)).toHaveCount(1);
    await expect(page.getByLabel("Garnfarbe")).toBeVisible();
    await closePopover(page);

    await runPreview(page);
    await openPopover(page, segment(page, "Farben"));
    // the sphere uses one colour the pattern leaves open: its field is the yarn colour
    await expect(colorInputs(page)).toHaveCount(1);
    await expect(page.getByLabel("Farbe A (Garnfarbe)")).toBeVisible();
  });

  test("Farbwechsel färbt das Canvas ohne neuen Request und schreibt params.color", async ({ page }) => {
    await startApp(page);
    await runPreview(page);
    const before = await page.locator("canvas").screenshot();
    const requests: string[] = [];
    page.on("request", (r) => void (r.url().includes("/api/") && requests.push(r.url())));

    await openPopover(page, segment(page, "Farben"));
    await page.getByLabel("Farbe A (Garnfarbe)").fill("#c0392b");
    await closePopover(page);
    await expect.poll(async () => (await page.locator("canvas").screenshot()).equals(before)).toBe(false);
    expect(requests.filter((u) => u.includes("/previews"))).toEqual([]);
    const stored = await page.evaluate(() => JSON.parse(localStorage.getItem("stitchcraft.params")!).color);
    expect(stored).toBe("#c0392b");
  });

  test("Roundtrip über .stitch.json", async ({ page }) => {
    await startApp(page);
    await openPopover(page, segment(page, "Farben"));
    await page.getByLabel("Garnfarbe").fill("#2e6fb5");
    await closePopover(page);
    await openPopover(page, menuButton(page));
    const [download] = await Promise.all([page.waitForEvent("download"), page.getByRole("button", { name: /Exportieren/ }).click()]);
    const saved = JSON.parse(await (await import("node:fs/promises")).readFile((await download.path())!, "utf8"));
    expect(saved.params.color).toBe("#2e6fb5");
    expect(saved.colorRule).toBe(2); // marks the file as already migrated

    await openPopover(page, segment(page, "Farben"));
    await page.getByLabel("Garnfarbe").fill("#000000");
    await closePopover(page);
    await importStitchFile(page, (await download.path())!);
    await openPopover(page, segment(page, "Farben"));
    await expect(page.getByLabel("Garnfarbe")).toHaveValue("#2e6fb5");
  });

  test("alte Datei mit colorPicks für die erste offene Farbe wird migriert", async ({ page }) => {
    await startApp(page);
    const old = { format: "stitchcraft", version: 1, text: SPHERE.join("\n"), dialect: "de", colors: { "A:#efe6d2": "#3366cc" } };
    await importStitchFile(page, { name: "alt.stitch.json", mimeType: "application/json", buffer: Buffer.from(JSON.stringify(old)) });
    await expect.poll(() => editorText(page)).toBe(SPHERE.join("\n"));
    await openPopover(page, segment(page, "Farben"));
    await expect(page.getByLabel("Garnfarbe")).toHaveValue("#3366cc");
    await closePopover(page);
    const stored = await page.evaluate(() => [JSON.parse(localStorage.getItem("stitchcraft.params")!).color, JSON.parse(localStorage.getItem("stitchcraft.colors")!)]);
    expect(stored).toEqual(["#3366cc", {}]);
    await runPreview(page);
    await openPopover(page, segment(page, "Farben"));
    await expect(page.getByLabel("Farbe A (Garnfarbe)")).toHaveValue("#3366cc");
  });
});

test.describe("U4 Cursor", () => {
  for (const theme of ["dark", "light"] as const) {
    test(`Einfügemarke sichtbar mit Kontrast ≥ 3:1, aktive Zeile hervorgehoben (${theme})`, async ({ page }) => {
      await startWithTheme(page, theme);
      await editor(page).click();
      const cursor = page.locator(".cm-cursor").first();
      await expect(cursor).toBeVisible();
      const [caret, width] = await cursor.evaluate((el) => [getComputedStyle(el).borderLeftColor, getComputedStyle(el).borderLeftWidth]);
      const background = await page.locator(".cm-editor").evaluate((el) => getComputedStyle(el).backgroundColor);
      expect(width).toBe("2px");
      expect(contrast(caret, background)).toBeGreaterThanOrEqual(3);
      const active = page.locator(".cm-activeLine");
      await expect(active).toHaveCount(1);
      expect(await active.evaluate((el) => getComputedStyle(el).backgroundColor)).not.toBe(background);
    });
  }
});

test.describe("U6 Tastatur und A11y", () => {
  test("Escape schließt jedes Popover, der Fokus kehrt zum Auslöser zurück; Klick außerhalb schließt", async ({ page }) => {
    await startApp(page);
    await runPreview(page);
    const triggers = [
      segment(page, "Dialekt"), segment(page, "Garn"), segment(page, "Farben"), menuButton(page),
      page.getByRole("button", { name: "Werkzeuge" }), page.getByRole("button", { name: "Export", exact: true }), timeChip(page),
    ];
    for (const trigger of triggers) {
      await expect(trigger).toHaveAttribute("aria-haspopup", "dialog");
      await expect(trigger).toHaveAttribute("aria-expanded", "false");
      await openPopover(page, trigger);
      await page.keyboard.press("Escape");
      await expect(page.getByRole("dialog")).toHaveCount(0);
      await expect(trigger).toHaveAttribute("aria-expanded", "false");
      await expect(trigger).toBeFocused();
    }
    await openPopover(page, segment(page, "Garn"));
    await editor(page).click();
    await expect(page.getByRole("dialog")).toHaveCount(0);
  });

  for (const theme of ["dark", "light"] as const) {
    test(`axe: keine Verstöße serious/critical auf der Hauptseite (${theme})`, async ({ page }) => {
      await startWithTheme(page, theme);
      await expect(page.locator(".status-bar")).toHaveText(/Keine Probleme/);
      const serious = async () =>
        (await new AxeBuilder({ page }).analyze()).violations
          .filter((v) => v.impact === "serious" || v.impact === "critical")
          .map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(" ")).join(", ")}`);
      expect(await serious()).toEqual([]);
      // with the yarn popover and the status details open
      await page.locator(".status-bar").click();
      await openPopover(page, segment(page, "Garn"));
      await page.getByRole("button", { name: "Mehr" }).click();
      expect(await serious()).toEqual([]);
      // the viewer with its floating controls and the tools popover
      await closePopover(page);
      await runPreview(page);
      await openPopover(page, page.getByRole("button", { name: "Werkzeuge" }));
      expect(await serious()).toEqual([]);
      // the time popover with pace, own pace and the rows
      await closePopover(page);
      await openPopover(page, timeChip(page));
      expect(await serious()).toEqual([]);
    });
  }
});

test.describe("U7 Mobil", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  const noHorizontalScroll = (page: Page) =>
    expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);

  test("kein horizontaler Scroll, Tabs und Bottom-Sheets funktionieren", async ({ page }) => {
    await startApp(page);
    await noHorizontalScroll(page);

    // popovers are bottom sheets: full width, at the bottom edge; Escape and the backdrop close them
    const sheet = await openPopover(page, segment(page, "Garn"));
    const box = (await sheet.boundingBox())!;
    expect(box.x).toBe(0);
    expect(box.width).toBe(375);
    expect(Math.round(box.y + box.height)).toBe(812);
    await noHorizontalScroll(page);
    await page.keyboard.press("Escape");
    await expect(sheet).toBeHidden();
    await openPopover(page, menuButton(page));
    await page.mouse.click(180, 40);
    await expect(page.getByRole("dialog")).toHaveCount(0);

    // no preview button on small screens: the 3D tab computes the preview
    await expect(page.getByRole("button", { name: "3D-Vorschau" })).toBeHidden();
    await page.getByRole("button", { name: "3D", exact: true }).click();
    await expect(page.locator("canvas")).toBeVisible({ timeout: 60_000 });
    await expect(page.getByRole("button", { name: "3D", exact: true })).toHaveAttribute("aria-pressed", "true");
    await expect(page.locator("canvas")).toBeVisible();
    await expect(editor(page)).toBeHidden();
    await noHorizontalScroll(page);
    const tools = await openPopover(page, page.getByRole("button", { name: "Werkzeuge" }));
    expect((await tools.boundingBox())!.width).toBe(375);
    await closePopover(page);

    await page.getByRole("button", { name: "Anleitung", exact: true }).click();
    await expect(editor(page)).toBeVisible();
    await expect(page.locator("canvas")).toBeHidden();
  });

  test("mit Fehlern in der Anleitung zeigt der 3D-Tab die letzte Vorschau", async ({ page }) => {
    await startApp(page);
    await page.getByRole("button", { name: "3D", exact: true }).click();
    await expect(page.locator("canvas")).toBeVisible({ timeout: 60_000 });
    await page.getByRole("button", { name: "Anleitung", exact: true }).click();
    const wrong = [...SPHERE];
    wrong[1] = "Rd. 2: 6x zun (13)";
    await typePattern(page, wrong);
    await expect(page.locator(".status-bar")).toHaveText(/^1 Fehler/);
    const previews: string[] = [];
    page.on("request", (r) => void (r.url().includes("/previews") && r.method() === "POST" && previews.push(r.url())));
    await page.getByRole("button", { name: "3D", exact: true }).click();
    await expect(page.locator("canvas")).toBeVisible();
    await expect(page.getByRole("button", { name: "3D", exact: true })).toHaveAttribute("aria-pressed", "true");
    expect(previews).toEqual([]);
  });
});

test("Snapshot-Modus behält seinen festen Hintergrund, unabhängig vom Theme", async ({ page }) => {
  const id = await createPreview(page, SPHERE);
  await page.goto("/?e2e");
  await page.evaluate(() => localStorage.setItem("stitchcraft.theme", JSON.stringify("dark")));
  await page.goto(`/?snapshot=${id}`);
  await expect.poll(() => page.evaluate(() => (window as unknown as { __stitchcraftSnapshot?: string }).__stitchcraftSnapshot), { timeout: 60_000 }).toBe("ready");
  await expect(page.locator("[data-snapshot]")).toHaveCSS("background-color", "rgb(235, 230, 222)");
  await expect(canvasBackground(page)).toHaveCSS("background-color", "rgb(235, 230, 222)");
});

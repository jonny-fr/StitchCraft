import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { contrast } from "./contrast";

type Tokens = Record<string, string>;

/** The `light-dark(<light>, <dark>)` colour tokens of app.css, per theme, with `var()` references resolved. */
function tokens(): { light: Tokens; dark: Tokens } {
  const css = readFileSync(new URL("./app.css", import.meta.url), "utf8");
  const root = /:root\s*\{([^}]*)\}/.exec(css)![1];
  const light: Tokens = {};
  const dark: Tokens = {};
  for (const [, name, value] of root.matchAll(/--([\w-]+):\s*([^;]+);/g)) {
    const pair = /^light-dark\((#[0-9a-f]{6}),\s*(#[0-9a-f]{6})\)$/i.exec(value);
    const ref = /^var\(--([\w-]+)\)$/.exec(value);
    if (pair) [light[name], dark[name]] = [pair[1], pair[2]];
    else if (ref && ref[1] in light) [light[name], dark[name]] = [light[ref[1]], dark[ref[1]]];
  }
  return { light, dark };
}

const SURFACES = ["bg", "card", "raised"];
const EDITOR = ["editor-bg", "editor-active-line"];
const HIGHLIGHT = ["hl-label", "hl-stitch", "hl-macro", "hl-modifier", "hl-meta", "hl-number"];
// [foreground, background, minimum]: text WCAG AA 4.5, muted text 3, non-text UI (caret, borders, focus ring) 3
const PAIRS: [string, string, number][] = [
  ...SURFACES.flatMap((s) => ["text", "error", "warning", "ok"].map((f): [string, string, number] => [f, s, 4.5])),
  ...SURFACES.map((s): [string, string, number] => ["muted", s, 3]),
  ["muted", "viewer-bg", 3],
  ["muted", "editor-bg", 3],
  ["on-accent", "accent", 4.5],
  ["text", "editor-selection", 4.5],
  ...EDITOR.flatMap((s) => ["text", ...HIGHLIGHT].map((f): [string, string, number] => [f, s, 4.5])),
  ["accent", "editor-bg", 3],
  ...SURFACES.map((s): [string, string, number] => ["accent", s, 3]),
  ...["card", "raised"].map((s): [string, string, number] => ["line-strong", s, 3]),
];

describe("design tokens", () => {
  const all = tokens();
  it("define every colour for both themes", () => {
    for (const name of [...SURFACES, ...EDITOR, ...HIGHLIGHT, "text", "muted", "accent", "on-accent", "viewer-bg", "editor-selection"])
      for (const theme of [all.light, all.dark]) expect(theme[name], name).toMatch(/^#[0-9a-f]{6}$/i);
  });
  for (const theme of ["light", "dark"] as const) {
    it.each(PAIRS)(`${theme}: %s on %s reaches %d:1`, (fg, bg, min) => {
      expect(contrast(all[theme][fg], all[theme][bg])).toBeGreaterThanOrEqual(min);
    });
  }
});

describe("contrast", () => {
  it("is 21 for black on white and symmetric", () => {
    expect(contrast("#000000", "#ffffff")).toBeCloseTo(21);
    expect(contrast("rgb(255, 255, 255)", "#000000")).toBeCloseTo(21);
  });
  it("is 1 for equal colours", () => expect(contrast("#777777", "#777777")).toBe(1));
});

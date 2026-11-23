import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { FIRST_FALLBACK, migrateOpenPick, openColor, paletteColors, pickColor } from "./colors";

const A = { ref: "A", hex: "#111111", defined: true };
const B = { ref: "B", hex: FIRST_FALLBACK, defined: false };
const C = { ref: "C", hex: "#c0392b", defined: false };
const palette = [A, B, C];

describe("openColor", () => {
  it("is the first entry the pattern leaves open, wherever it stands", () => expect(openColor(palette)).toBe(B));
  it("is undefined when the pattern defines every colour", () => expect(openColor([A])).toBeUndefined());
});

describe("paletteColors", () => {
  it("shows the yarn colour on the open entry and picks or pattern colours elsewhere", () => {
    expect([...paletteColors(palette, "#abcdef", { "A:#111111": "#00ff00", [`B:${FIRST_FALLBACK}`]: "#ff0000" })]).toEqual([
      ["A", "#00ff00"], ["B", "#abcdef"], ["C", "#c0392b"],
    ]);
  });
  it("replaces only the first undefined colour", () => {
    const p = [{ ...B, ref: "A" }, { ...C, ref: "B" }];
    expect([...paletteColors(p, "#abcdef")]).toEqual([["A", "#abcdef"], ["B", "#c0392b"]]);
  });
  it("keeps a palette without open entries", () => expect(paletteColors([A], "#abcdef").get("A")).toBe("#111111"));
});

describe("pickColor", () => {
  const state = { color: "#efe6d2", picks: {} };
  it("writes the yarn colour for the first open entry", () => {
    expect(pickColor(palette, B, "#ff0000", state)).toEqual({ color: "#ff0000", picks: {} });
  });
  it("writes a pick for every other entry, defined or open", () => {
    expect(pickColor(palette, A, "#ff0000", state)).toEqual({ color: "#efe6d2", picks: { "A:#111111": "#ff0000" } });
    expect(pickColor(palette, C, "#00ff00", state)).toEqual({ color: "#efe6d2", picks: { "C:#c0392b": "#00ff00" } });
  });
  it("is the only setting: a changed yarn colour shows on the open entry", () => {
    const next = pickColor(palette, B, "#123456", state);
    expect(paletteColors(palette, next.color, next.picks).get("B")).toBe("#123456");
  });
});

describe("migrateOpenPick", () => {
  it("moves a pick for the first open colour into the yarn colour and drops it", () => {
    expect(migrateOpenPick({ color: "#efe6d2", picks: { [`A:${FIRST_FALLBACK}`]: "#FF0000", "B:#c0392b": "#00ff00" } })).toEqual({
      color: "#ff0000", picks: { "B:#c0392b": "#00ff00" },
    });
  });
  it("leaves state without such a pick alone", () => {
    const s = { color: "#efe6d2", picks: { "B:#c0392b": "#00ff00" } };
    expect(migrateOpenPick(s)).toBe(s);
  });
  it("drops an invalid pick without touching the yarn colour", () => {
    expect(migrateOpenPick({ color: "#123456", picks: { [`A:${FIRST_FALLBACK}`]: "red" } })).toEqual({ color: "#123456", picks: {} });
  });
});

it("FIRST_FALLBACK is the server's first fallback colour", () => {
  const toml = readFileSync(new URL("../../data/colors.toml", import.meta.url), "utf8");
  expect(toml.match(/^defaults = \["(#[0-9a-f]{6})"/m)?.[1]).toBe(FIRST_FALLBACK);
});

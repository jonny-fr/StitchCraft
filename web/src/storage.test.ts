// @vitest-environment jsdom
import { beforeEach, describe, expect, it, vi } from "vitest";
import { defaultParams } from "./api";
import { KEYS, load, loadColors, loadDialect, loadParams, loadString, save } from "./storage";

beforeEach(() => localStorage.clear());

describe("load/save", () => {
  it("round-trips JSON values", () => {
    save("k", { a: [1, 2] });
    expect(load("k", null)).toEqual({ a: [1, 2] });
  });
  it("falls back when missing or corrupt", () => {
    expect(load("missing", 7)).toBe(7);
    localStorage.setItem("k", "{not json");
    expect(load("k", 7)).toBe(7);
  });
  it("survives unavailable storage", () => {
    const get = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("denied"); });
    const set = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("quota"); });
    expect(load("k", "fb")).toBe("fb");
    expect(() => save("k", 1)).not.toThrow();
    get.mockRestore();
    set.mockRestore();
  });
});

describe("loadParams", () => {
  it("returns defaults when nothing is stored", () => expect(loadParams()).toEqual(defaultParams));
  it("merges partial stored values over the defaults", () => {
    save(KEYS.params, { yarn_mm: 4, hook_mm: 5 });
    expect(loadParams()).toEqual({ ...defaultParams, yarn_mm: 4, hook_mm: 5 });
  });
  it.each([
    ["out of range", { yarn_mm: 99 }],
    ["wrong type", { fill: "lots" }],
    ["unknown material", { material: "silk" }],
    ["bad colour", { color: "red" }],
  ])("gives the defaults for %s", (_, bad) => {
    save(KEYS.params, { ...defaultParams, ...bad });
    expect(loadParams()).toEqual(defaultParams);
  });
  it.each([["null", "null"], ["array", "[1]"], ["string", '"x"'], ["corrupt", "{"]])("gives the defaults for %s", (_, raw) => {
    localStorage.setItem(KEYS.params, raw);
    expect(loadParams()).toEqual(defaultParams);
  });
});

describe("loadString / loadDialect", () => {
  it("accepts strings only", () => {
    save(KEYS.text, "Rd. 1: 6 fM in MR (6)");
    expect(loadString(KEYS.text, "x")).toBe("Rd. 1: 6 fM in MR (6)");
    save(KEYS.text, 42);
    expect(loadString(KEYS.text, "x")).toBe("x");
  });
  it("keeps a valid dialect and resets an unknown one", () => {
    expect(loadDialect()).toBe("de");
    save(KEYS.dialect, "en-UK");
    expect(loadDialect()).toBe("en-UK");
    save(KEYS.dialect, "klingon");
    expect(loadDialect()).toBe("de");
  });
});

describe("loadColors", () => {
  it("keeps string entries and drops the rest", () => {
    save(KEYS.colors, { "A:#fff000": "#ff0000", B: 3 });
    expect(loadColors()).toEqual({ "A:#fff000": "#ff0000" });
  });
  it("gives an empty map for non-objects", () => {
    save(KEYS.colors, [1]);
    expect(loadColors()).toEqual({});
  });
});

import { describe, expect, it } from "vitest";
import { defaultParams } from "./api";
import { parseStitchFile, serializeStitchFile, stitchFileName } from "./stitchFile";

const file = {
  text: "Rd. 1: 6 fM in MR (6)",
  dialect: "de",
  params: { ...defaultParams, material: "mohair" as const, right_side_out: false, gauge_stitches: 14 },
  colors: { "A:#efe6d2": "#ff0000" }, // a pick for a pattern colour that is "creme" itself: no migration
};

describe("stitch file", () => {
  it("round-trips", () => {
    expect(parseStitchFile(serializeStitchFile(file))).toEqual({ ok: true, file });
  });
  it("writes format, version and the colour rule", () => {
    expect(JSON.parse(serializeStitchFile(file))).toMatchObject({ format: "stitchcraft", version: 1, colorRule: 2 });
  });
  it("rejects broken JSON, foreign formats and unknown versions", () => {
    expect(parseStitchFile("{nope")).toEqual({ ok: false, error: "badJson" });
    expect(parseStitchFile('{"format":"other","text":""}')).toEqual({ ok: false, error: "notStitchFile" });
    expect(parseStitchFile("[]")).toEqual({ ok: false, error: "notStitchFile" });
    expect(parseStitchFile('{"format":"stitchcraft","version":2,"text":""}')).toEqual({ ok: false, error: "badVersion" });
  });
  it("falls back to defaults for missing or invalid params", () => {
    const raw = JSON.stringify({ format: "stitchcraft", version: 1, text: "x", dialect: "fr", params: { yarn_mm: 99, hook_mm: 4, material: "silk" }, colors: { a: "red", b: "#00ff00" } });
    const r = parseStitchFile(raw);
    expect(r.ok && r.file).toEqual({
      text: "x", dialect: "de", params: { ...defaultParams, hook_mm: 4 }, colors: { b: "#00ff00" },
    });
  });
  it("moves an old pick for the first open colour into params.color, once", () => {
    const old = JSON.parse(serializeStitchFile({ ...file, colors: { "A:#efe6d2": "#ff0000", "B:#c0392b": "#00ff00" } }));
    delete old.colorRule; // written before the marker existed
    const r = parseStitchFile(JSON.stringify(old));
    expect(r.ok && r.file.params.color).toBe("#ff0000");
    expect(r.ok && r.file.colors).toEqual({ "B:#c0392b": "#00ff00" });
    // exported again, the file carries the marker and is not migrated a second time
    expect(r.ok && parseStitchFile(serializeStitchFile(r.file))).toEqual(r);
  });
  it("accepts a file without params and colors", () => {
    const r = parseStitchFile('{"format":"stitchcraft","version":1,"text":"x"}');
    expect(r.ok && r.file.params).toEqual(defaultParams);
  });
});

describe("stitchFileName", () => {
  it("uses a title line", () => expect(stitchFileName("Kleiner Bär\nRd. 1: 6 fM")).toBe("kleiner-bar.stitch.json"));
  it("falls back for row lines and empty text", () => {
    expect(stitchFileName("Rd. 1: 6 fM in MR")).toBe("pattern.stitch.json");
    expect(stitchFileName("")).toBe("pattern.stitch.json");
    expect(stitchFileName("6 fM in MR")).toBe("pattern.stitch.json");
  });
});

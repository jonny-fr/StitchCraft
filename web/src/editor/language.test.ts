import { describe, expect, it } from "vitest";
import { countMarkers, scanLine, wordAt, type Word } from "./language";

const words: Word[] = [
  { word: "fM", category: "stitch", canonical: "sc" },
  { word: "feste Masche", category: "stitch", canonical: "sc" },
  { word: "zun", category: "macro", canonical: "inc" },
  { word: "Rd.", category: "label", canonical: "round" },
  { word: "R", category: "label", canonical: "row_label_short" },
  { word: "in MR", category: "ring", canonical: "ring" },
  { word: "MR", category: "ring", canonical: "ring" },
  { word: "nur hMg", category: "loop", canonical: "blo" },
  { word: "sc", category: "stitch", canonical: "sc" },
];

describe("scanLine", () => {
  it("splits a round into typed tokens", () => {
    const toks = scanLine("Rd. 2: (1 fM, zun) x6 (18)", words).map((t) => [t.text, t.type]);
    expect(toks).toEqual([
      ["Rd.", "label"],
      ["2", "number"],
      ["1", "number"],
      ["fM", "stitch"],
      ["zun", "macro"],
      ["x6", "number"],
      ["(18)", "count"],
    ]);
  });

  it("prefers the longest word and respects word boundaries", () => {
    const toks = scanLine("6 feste Masche in MR, MRX, fMx", words).map((t) => t.text);
    expect(toks).toEqual(["6", "feste Masche", "in MR"]);
  });

  it("lets a digit touch labels and stitches", () => {
    expect(scanLine("R1: sc2tog", words).map((t) => t.type)).toEqual(["label", "number", "stitch", "number"]);
  });
});

describe("wordAt", () => {
  it("finds the vocabulary word under the caret", () => {
    const text = "Rd. 6: nur hMg 30 fM";
    expect(wordAt(text, text.indexOf("hMg"), words)?.canonical).toBe("blo");
    expect(wordAt(text, text.indexOf("fM") + 1, words)?.word).toBe("fM");
    expect(wordAt(text, text.indexOf("30"), words)).toBeNull();
  });
});

describe("countMarkers", () => {
  it("shows the count of each row line and flags mismatches", () => {
    const m = countMarkers([
      { number: 1, kind: "round", actual: 6, expected: 6, line: 1 },
      { number: 2, kind: "round", actual: 12, expected: 13, line: 2 },
      { number: 3, kind: "round", actual: 12, expected: null, line: 3 },
      { number: 4, kind: "round", actual: 12, expected: null, line: 3 },
    ]);
    expect(m.get(1)).toEqual({ label: "6", bad: false });
    expect(m.get(2)).toEqual({ label: "12≠13", bad: true });
    expect(m.get(3)).toEqual({ label: "12", bad: false });
  });
});

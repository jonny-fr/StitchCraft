import i18next, { type TFunction } from "i18next";
import { beforeAll, describe, expect, it } from "vitest";
import type { TimeEstimate } from "./api";
import de from "./i18n/locales/de.json";
import en from "./i18n/locales/en.json";
import { defaultPace, formatDuration, formatRange, sanitizePace, secondsUpTo } from "./time";

let tDe: TFunction;
let tEn: TFunction;
beforeAll(async () => {
  const i18n = i18next.createInstance();
  await i18n.init({ resources: { de: { translation: de }, en: { translation: en } }, lng: "de", interpolation: { escapeValue: false } });
  [tDe, tEn] = [i18n.getFixedT("de"), i18n.getFixedT("en")];
});

const min = (m: number) => m * 60;
const hours = (h: number) => h * 3600;

describe("formatRange", () => {
  it("shows minutes below an hour, in steps of 5 from 10 min", () => {
    expect(formatRange(tDe, 980, 1632)).toBe("≈ 15–25 min"); // the reference sphere at the practised pace
    expect(formatRange(tDe, min(3.4), min(5.6))).toBe("≈ 3–6 min");
    expect(formatRange(tDe, 40, 66)).toBe("≈ 1 min");
  });
  it("shows hours in steps of ½ once the upper end reaches an hour", () => {
    expect(formatRange(tDe, hours(2.4), hours(3.1))).toBe("≈ 2½–3 h");
    expect(formatRange(tDe, min(45), min(75))).toBe("≈ 1–1½ h");
    expect(formatRange(tDe, min(20), min(61))).toBe("≈ ½–1 h");
  });
  it("is the same in English", () => {
    expect(formatRange(tEn, hours(2.4), hours(3.1))).toBe("≈ 2½–3 h");
    expect(formatRange(tEn, 980, 1632)).toBe("≈ 15–25 min");
  });
  it("says less than a minute for tiny pieces", () => expect(formatRange(tDe, 20, 40)).toBe("< 1 min"));
});

describe("formatDuration", () => {
  it("rounds like the range", () => {
    expect(formatDuration(tDe, 30)).toBe("< 1 min");
    expect(formatDuration(tDe, min(7.4))).toBe("≈ 7 min");
    expect(formatDuration(tDe, min(23))).toBe("≈ 25 min");
    expect(formatDuration(tEn, hours(1.6))).toBe("≈ 1½ h");
  });
});

describe("secondsUpTo", () => {
  const est: TimeEstimate = {
    seconds_low: 0, seconds_high: 0,
    per_row: [{ number: 1, kind: "round", seconds: 50 }, { number: 2, kind: "round", seconds: 70 }, { number: 3, kind: "round", seconds: 100 }],
  };
  it("sums the rows up to and including the given one", () => {
    expect(secondsUpTo(est, 2)).toBe(120);
    expect(secondsUpTo(est, 99)).toBe(220);
    expect(secondsUpTo(est, 0)).toBe(0);
  });
});

describe("sanitizePace", () => {
  it("keeps a valid setting", () => expect(sanitizePace({ pace: "schnell", stitchesPerMinute: 18 })).toEqual({ pace: "schnell", stitchesPerMinute: 18 }));
  it.each([null, "fast", [], { pace: "turbo", stitchesPerMinute: -1 }, { stitchesPerMinute: 500 }])("falls back for %j", (raw) => {
    expect(sanitizePace(raw)).toEqual(defaultPace);
  });
});

import { defaultParams, paramsValid, type Params } from "./api";

export const KEYS = {
  text: "stitchcraft.text",
  dialect: "stitchcraft.dialect",
  params: "stitchcraft.params",
  colors: "stitchcraft.colors",
  lang: "stitchcraft.lang",
} as const;

export function load<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

export function save(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage unavailable: keep working without persistence */
  }
}

/** Stored params merged over the defaults; anything invalid gives the defaults. */
export function loadParams(): Params {
  const stored = load<unknown>(KEYS.params, {});
  const merged = { ...defaultParams, ...(typeof stored === "object" && stored !== null && !Array.isArray(stored) ? stored : {}) };
  return paramsValid(merged) ? merged : defaultParams;
}

export const DIALECT_IDS = ["auto", "de", "en-US", "en-UK"];

export function loadDialect(): string {
  const v = loadString(KEYS.dialect, "de");
  return DIALECT_IDS.includes(v) ? v : "de";
}

export function loadString(key: string, fallback: string): string {
  const v = load<unknown>(key, fallback);
  return typeof v === "string" ? v : fallback;
}

/** Colour picks: a map of strings, other entries dropped. */
export function loadColors(): Record<string, string> {
  const v = load<unknown>(KEYS.colors, {});
  if (typeof v !== "object" || v === null || Array.isArray(v)) return {};
  return Object.fromEntries(Object.entries(v).filter(([, c]) => typeof c === "string")) as Record<string, string>;
}

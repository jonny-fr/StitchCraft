import { defaultParams, paramsValid, type Params } from "./api";
import { COLOR_RULE, migrateOpenPick, type ColorPicks } from "./colors";
import { DIALECT_IDS } from "./dialects";
import { THEMES, type Theme } from "./theme";

export const KEYS = {
  text: "stitchcraft.text",
  dialect: "stitchcraft.dialect",
  params: "stitchcraft.params",
  colors: "stitchcraft.colors",
  colorRule: "stitchcraft.colorRule",
  lang: "stitchcraft.lang",
  theme: "stitchcraft.theme",
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

export function loadDialect(): string {
  const v = loadString(KEYS.dialect, "de");
  return DIALECT_IDS.includes(v) ? v : "de";
}

export function loadString(key: string, fallback: string): string {
  const v = load<unknown>(key, fallback);
  return typeof v === "string" ? v : fallback;
}

/** Colour picks: a map of strings, other entries dropped. */
export function loadColors(): ColorPicks {
  const v = load<unknown>(KEYS.colors, {});
  if (typeof v !== "object" || v === null || Array.isArray(v)) return {};
  return Object.fromEntries(Object.entries(v).filter(([, c]) => typeof c === "string")) as ColorPicks;
}

/** Params and colour picks; stored data from before COLOR_RULE is migrated once, saved and marked. */
export function loadColorSettings(): { params: Params; picks: ColorPicks } {
  const params = loadParams();
  const picks = loadColors();
  if (load<unknown>(KEYS.colorRule, null) === COLOR_RULE) return { params, picks };
  const migrated = migrateOpenPick({ color: params.color, picks });
  const out = { params: { ...params, color: migrated.color }, picks: migrated.picks };
  save(KEYS.params, out.params);
  save(KEYS.colors, out.picks);
  save(KEYS.colorRule, COLOR_RULE);
  return out;
}

/** The UI theme; dark unless another one was chosen. */
export function loadTheme(): Theme {
  const v = loadString(KEYS.theme, "dark");
  return (THEMES as readonly string[]).includes(v) ? (v as Theme) : "dark";
}

import { defaultParams, paramsValid, type Params } from "./api";
import { migrateOpenPick, type ColorPicks } from "./colors";
import { DIALECT_IDS } from "./dialects";

export interface StitchFile {
  text: string;
  dialect: string;
  params: Params;
  colors: ColorPicks;
}

export type StitchFileError = "badJson" | "notStitchFile" | "badVersion";
export type ParsedStitchFile = { ok: true; file: StitchFile } | { ok: false; error: StitchFileError };

const FORMAT = "stitchcraft";
const VERSION = 1;

export function serializeStitchFile(file: StitchFile): string {
  return JSON.stringify({ format: FORMAT, version: VERSION, ...file }, null, 2);
}

const isRecord = (v: unknown): v is Record<string, unknown> => typeof v === "object" && v !== null && !Array.isArray(v);

/** Imported params: each invalid or missing field falls back to its default. */
function sanitizeParams(raw: unknown): Params {
  const out: Params = { ...defaultParams };
  if (!isRecord(raw)) return out;
  for (const key of Object.keys(defaultParams) as (keyof Params)[]) {
    const candidate = { ...out, [key]: raw[key] } as Params;
    if (key in raw && paramsValid(candidate)) (out as unknown as Record<string, unknown>)[key] = raw[key];
  }
  return out;
}

export function parseStitchFile(raw: string): ParsedStitchFile {
  let data: unknown;
  try {
    data = JSON.parse(raw);
  } catch {
    return { ok: false, error: "badJson" };
  }
  if (!isRecord(data) || data.format !== FORMAT || typeof data.text !== "string") return { ok: false, error: "notStitchFile" };
  if (data.version !== VERSION) return { ok: false, error: "badVersion" };
  const picks: ColorPicks = {};
  if (isRecord(data.colors)) {
    for (const [k, v] of Object.entries(data.colors)) if (typeof v === "string" && /^#[0-9a-f]{6}$/i.test(v)) picks[k] = v;
  }
  const params = sanitizeParams(data.params);
  // older files kept the first open colour as a pick; it lives in params.color now
  const { color, picks: colors } = migrateOpenPick({ color: params.color, picks });
  return {
    ok: true,
    file: {
      text: data.text,
      dialect: typeof data.dialect === "string" && DIALECT_IDS.includes(data.dialect) ? data.dialect : "de",
      params: { ...params, color },
      colors,
    },
  };
}

/** `my-hat.stitch.json` from a leading title line; row lines and empty titles give `pattern.stitch.json`. */
export function stitchFileName(text: string): string {
  const first = text.split("\n").find((l) => l.trim() !== "") ?? "";
  const isRow = /^\s*(r|rd|rnd|reihe|runde|round|row)\b/i.test(first) || /^\s*\d/.test(first);
  const slug = first.normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40);
  return `${isRow || !slug ? "pattern" : slug}.stitch.json`;
}

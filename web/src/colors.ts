import type { PaletteColor } from "./api";

/** Colour the server gives the first palette entry a pattern leaves open (`defaults[0]` in data/colors.toml). */
export const FIRST_FALLBACK = "#efe6d2";

/** Colours picked in the UI, keyed by palette code and the colour the pattern gave it. */
export type ColorPicks = Record<string, string>;

/** The yarn colour (`params.color`) together with the picks: everything the colour setting writes. */
export interface ColorState { color: string; picks: ColorPicks }

export const pickKey = (c: PaletteColor) => `${c.ref}:${c.hex}`;

/** The palette entry that shows the yarn colour: the first one the pattern leaves open. */
export const openColor = (palette: PaletteColor[]) => palette.find((c) => !c.defined);

/** Shown colour per palette code: the open entry shows `color`, every other entry its pick or the pattern's colour. */
export function paletteColors(palette: PaletteColor[], color: string, picks: ColorPicks = {}): Map<string, string> {
  const open = openColor(palette);
  return new Map(palette.map((c) => [c.ref, c === open ? color : (picks[pickKey(c)] ?? c.hex)]));
}

/** A colour change: the open entry writes the yarn colour, every other entry a pick. */
export function pickColor(palette: PaletteColor[], entry: PaletteColor, hex: string, state: ColorState): ColorState {
  if (entry === openColor(palette)) return { ...state, color: hex };
  return { ...state, picks: { ...state.picks, [pickKey(entry)]: hex } };
}

/**
 * Version of the colour rule above. Data from rule 1 (no marker) could also hold a pick for the first open entry;
 * it is migrated once with `migrateOpenPick` and then marked with this version, so later picks stay untouched.
 */
export const COLOR_RULE = 2;

/**
 * One-time migration of rule-1 data: picks for a first open entry (key `<code>:FIRST_FALLBACK`) move into the yarn
 * colour. Without the palette the key is all there is to go by, so a rule-1 pick for a pattern colour that is itself
 * FIRST_FALLBACK ("creme") moves too; run it only on data without the COLOR_RULE marker.
 */
export function migrateOpenPick(state: ColorState): ColorState {
  const open = Object.keys(state.picks).filter((k) => k.endsWith(`:${FIRST_FALLBACK}`));
  if (!open.length) return state;
  const picks = Object.fromEntries(Object.entries(state.picks).filter(([k]) => !open.includes(k)));
  const moved = state.picks[open[0]];
  return { color: /^#[0-9a-f]{6}$/i.test(moved) ? moved.toLowerCase() : state.color, picks };
}

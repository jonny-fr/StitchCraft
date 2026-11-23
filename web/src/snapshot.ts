import { MATERIALS, type Material, type PaletteColor } from "./api";
import type { View } from "./viewer/Viewer";

export const VIEWS: View[] = ["front", "side", "top", "iso"];

export interface SnapshotQuery { key: string; view: View; color: string; material: Material }

/** `?snapshot=<key>&view=front&color=efe6d2&material=cotton`; null when the page is not in snapshot mode or the query is invalid. */
export function parseSnapshotQuery(search: string): SnapshotQuery | null {
  const q = new URLSearchParams(search);
  const key = q.get("snapshot");
  if (key === null) return null;
  const view = (q.get("view") ?? "front") as View;
  const color = (q.get("color") ?? "efe6d2").replace(/^#/, "").toLowerCase();
  const material = (q.get("material") ?? "cotton") as Material;
  if (!/^[0-9a-zA-Z]+$/.test(key) || !VIEWS.includes(view) || !/^[0-9a-f]{6}$/.test(color) || !MATERIALS.includes(material)) return null;
  return { key, view, color: `#${color}`, material };
}

/** Same rule as the editor: the first palette colour the pattern leaves open takes the yarn colour. */
export function paletteColors(palette: PaletteColor[], color: string): Map<string, string> {
  return new Map(palette.map((c) => [c.ref, !c.defined && c.ref === palette[0]?.ref ? color : c.hex]));
}

import { describe, expect, it } from "vitest";
import de from "./locales/de.json";
import en from "./locales/en.json";

type Tree = { [k: string]: string | Tree };

function leaves(tree: Tree, prefix = ""): Map<string, string> {
  const out = new Map<string, string>();
  for (const [k, v] of Object.entries(tree)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (typeof v === "string") out.set(key, v);
    else for (const [kk, vv] of leaves(v, key)) out.set(kk, vv);
  }
  return out;
}

const placeholders = (s: string) => [...s.matchAll(/\{\{\s*(\w+)\s*\}\}/g)].map((m) => m[1]).sort();
const [deLeaves, enLeaves] = [leaves(de as Tree), leaves(en as Tree)];

describe("locale catalogs", () => {
  it("have the same keys", () => {
    const keys = (m: Map<string, string>) => [...m.keys()].sort();
    expect(keys(enLeaves)).toEqual(keys(deLeaves));
  });
  it("have no empty strings", () => {
    for (const [name, m] of [["de", deLeaves], ["en", enLeaves]] as const)
      for (const [k, v] of m) expect(v.trim(), `${name}:${k}`).not.toBe("");
  });
  it("use the same interpolation placeholders per key", () => {
    for (const [k, v] of deLeaves) expect(placeholders(enLeaves.get(k) ?? ""), k).toEqual(placeholders(v));
  });
});

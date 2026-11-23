/** Standard yarn weight classes (CYCA 0-7): typical strand diameter and recommended hook. */
export interface YarnClass { id: string; yarn_mm: number; hook_mm: number }

export const YARN_CLASSES: YarnClass[] = [
  { id: "lace", yarn_mm: 0.8, hook_mm: 1.75 },
  { id: "fingering", yarn_mm: 1.2, hook_mm: 2.5 },
  { id: "sport", yarn_mm: 1.6, hook_mm: 3.0 },
  { id: "dk", yarn_mm: 2.0, hook_mm: 3.5 },
  { id: "worsted", yarn_mm: 2.5, hook_mm: 4.5 },
  { id: "bulky", yarn_mm: 4.5, hook_mm: 6.5 },
  { id: "superBulky", yarn_mm: 6.5, hook_mm: 9.0 },
  { id: "jumbo", yarn_mm: 10.0, hook_mm: 15.0 },
];

/** The class whose diameter equals `yarn_mm`, or null for a custom thickness. */
export function yarnClassOf(yarn_mm: number): YarnClass | null {
  return YARN_CLASSES.find((c) => Math.abs(c.yarn_mm - yarn_mm) < 0.005) ?? null;
}

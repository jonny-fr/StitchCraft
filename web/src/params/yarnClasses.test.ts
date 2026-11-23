import { describe, expect, it } from "vitest";
import { defaultParams, paramsValid } from "../api";
import { YARN_CLASSES, yarnClassOf } from "./yarnClasses";

describe("yarn classes", () => {
  it("default params are DK", () => {
    const dk = yarnClassOf(defaultParams.yarn_mm);
    expect(dk?.id).toBe("dk");
    expect(dk?.hook_mm).toBe(defaultParams.hook_mm);
  });
  it("unmatched thickness is custom", () => {
    expect(yarnClassOf(2.3)).toBeNull();
  });
  it("every class stays inside the server bounds", () => {
    for (const c of YARN_CLASSES) expect(paramsValid({ ...defaultParams, yarn_mm: c.yarn_mm, hook_mm: c.hook_mm })).toBe(true);
  });
});

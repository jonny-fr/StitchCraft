export const VIEWS = ["front", "side", "top", "iso"];
export const MATERIALS = ["cotton", "acrylic", "mohair"];
export const LIMITS = { minSize: 64, maxSize: 2048, defaultWidth: 800, defaultHeight: 600 };

export class InputError extends Error {}

/** Checks a /render body and returns normalised options; throws InputError naming the bad field. */
export function parseRequest(body) {
  if (body === null || typeof body !== "object" || Array.isArray(body)) throw new InputError("body must be a JSON object");
  const { key, view = "front", color = "efe6d2", material = "cotton", width = LIMITS.defaultWidth, height = LIMITS.defaultHeight } = body;
  if (typeof key !== "string" || !/^[0-9a-zA-Z]{1,64}$/.test(key)) throw new InputError("key: expected 1-64 alphanumeric characters");
  if (!VIEWS.includes(view)) throw new InputError(`view: expected one of ${VIEWS.join(", ")}`);
  if (typeof color !== "string" || !/^[0-9a-fA-F]{6}$/.test(color)) throw new InputError("color: expected 6 hex digits without #");
  if (!MATERIALS.includes(material)) throw new InputError(`material: expected one of ${MATERIALS.join(", ")}`);
  for (const [name, v] of [["width", width], ["height", height]]) {
    if (!Number.isInteger(v) || v < LIMITS.minSize || v > LIMITS.maxSize)
      throw new InputError(`${name}: expected an integer from ${LIMITS.minSize} to ${LIMITS.maxSize}`);
  }
  return { key, view, color: color.toLowerCase(), material, width, height };
}

export function snapshotQuery({ key, view, color, material }) {
  return new URLSearchParams({ snapshot: key, view, color, material }).toString();
}

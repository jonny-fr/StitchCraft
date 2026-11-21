import { decodeYarnBin, type Yarn } from "./viewer/yarn";

export interface Span { start: number; end: number; line: number; col: number }
export interface Diagnostic { code: string; severity: "error" | "warning" | "info"; span: Span | null; params: Record<string, unknown> }
export interface RowCount { number: number; kind: string; actual: number; expected: number | null }
export interface Validation { dialect: string; ok: boolean; total_stitches: number; diagnostics: Diagnostic[]; rows: RowCount[] }
export interface Params {
  yarn_mm: number; hook_mm: number; gauge_stitches: number | null; gauge_rows: number | null;
  fill: number; handedness: "right" | "left"; color: string;
}
export interface StitchInfo { id: number; row: number; type: string; op: string | null; span: Span | null; position: number[]; parents: number[] }
export interface Shape { key: string; stats: Stats; stitches: StitchInfo[]; rows: { number: number; kind: string; stitches: number }[] }
export interface Stats { stitches: number; rows: number; size_cm: number[]; yarn_length_m: number; timings: Record<string, number> }
export interface PreviewResult { id: string; yarn: Yarn; shape: Shape }

export const defaultParams: Params = {
  yarn_mm: 2.0, hook_mm: 3.5, gauge_stitches: null, gauge_rows: null, fill: 0.7, handedness: "right", color: "#efe6d2",
};

/** Mirrors the server's ParamsIn bounds, so invalid input never leaves the browser. */
export function paramsValid(p: Params): boolean {
  const within = (v: number, lo: number, hi: number) => Number.isFinite(v) && v > lo && v < hi;
  const gauge = (v: number | null) => v === null || within(v, 1, 100);
  return within(p.yarn_mm, 0.3, 15) && within(p.hook_mm, 0.5, 25) && gauge(p.gauge_stitches) && gauge(p.gauge_rows)
    && p.fill >= 0 && p.fill <= 1 && /^#[0-9a-f]{6}$/i.test(p.color);
}

/** HTTP failure; `diagnostics` is set when the server explained the rejection. */
export class ApiError extends Error {
  constructor(status: number, readonly diagnostics: Diagnostic[] = []) {
    super(`HTTP ${status}`);
  }
}

async function ok(res: Response): Promise<Response> {
  if (res.ok) return res;
  const body = await res.json().catch(() => null);
  const diagnostics = body?.detail?.diagnostics;
  throw new ApiError(res.status, Array.isArray(diagnostics) ? diagnostics : []);
}

async function json<T>(res: Response): Promise<T> {
  return (await ok(res)).json() as Promise<T>;
}

export async function validate(text: string, dialect: string, signal?: AbortSignal): Promise<Validation> {
  const res = await fetch("/api/v1/validate", {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ text, dialect }), signal,
  });
  return json<Validation>(res);
}

export async function requestPreview(text: string, dialect: string, params: Params): Promise<PreviewResult> {
  const res = await fetch("/api/v1/previews", {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ text, dialect, params }),
  });
  const { id } = await json<{ id: string }>(res);
  const [bin, shape] = await Promise.all([
    fetch(`/api/v1/previews/${id}/yarn.bin`).then(ok).then((r) => r.arrayBuffer()),
    fetch(`/api/v1/previews/${id}/shape.json`).then((r) => json<Shape>(r)),
  ]);
  return { id, yarn: decodeYarnBin(bin), shape };
}

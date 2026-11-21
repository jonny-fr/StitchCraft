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
export interface Shape { key: string; stats: Stats; stitches: StitchInfo[]; rows: { number: number; stitches: number }[] }
export interface Stats { stitches: number; rows: number; size_cm: number[]; yarn_length_m: number; timings: Record<string, number> }
export interface PreviewResult { id: string; yarn: Yarn; shape: Shape }

export const defaultParams: Params = {
  yarn_mm: 2.0, hook_mm: 3.5, gauge_stitches: null, gauge_rows: null, fill: 0.7, handedness: "right", color: "#efe6d2",
};

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) throw Object.assign(new Error(`HTTP ${res.status}`), { body: await res.json().catch(() => null) });
  return res.json() as Promise<T>;
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
    fetch(`/api/v1/previews/${id}/yarn.bin`).then((r) => r.arrayBuffer()),
    fetch(`/api/v1/previews/${id}/shape.json`).then((r) => json<Shape>(r)),
  ]);
  return { id, yarn: decodeYarnBin(bin), shape };
}

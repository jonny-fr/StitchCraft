import { useEffect, useMemo, useState } from "react";
import { loadPreview, type PreviewResult } from "./api";
import { paletteColors, type SnapshotQuery } from "./snapshot";
import { Viewer } from "./viewer/Viewer";

type Status = "loading" | "ready" | "error";
const SETTLE_FRAMES = 20; // the first frames still load the environment and run the AO pass

/** Headless render target for the snapshot service: only the viewer, full screen, no controls. */
export default function SnapshotPage({ query }: { query: SnapshotQuery }) {
  const [result, setResult] = useState<PreviewResult | null>(null);
  const [status, setStatus] = useState<Status>("loading");

  useEffect(() => {
    let cancelled = false;
    loadPreview(query.key).then(
      (r) => !cancelled && setResult(r),
      () => !cancelled && setStatus("error"),
    );
    return () => void (cancelled = true);
  }, [query.key]);

  useEffect(() => {
    if (!result) return;
    let frames = 0;
    let raf = 0;
    const tick = () => {
      if (document.querySelector("canvas") && ++frames >= SETTLE_FRAMES) return setStatus("ready");
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [result]);

  useEffect(() => {
    (window as unknown as { __stitchcraftSnapshot: Status }).__stitchcraftSnapshot = status;
  }, [status]);

  const { rowOf, colorOf, maxRow, rounds } = useMemo(() => {
    const shape = result?.shape;
    const hex = paletteColors(shape?.palette ?? [], query.color);
    return {
      rowOf: new Map(shape?.stitches.map((s) => [s.id, s.row]) ?? []),
      colorOf: new Map(shape?.stitches.map((s) => [s.id, hex.get(s.color) ?? "#ffffff"]) ?? []),
      maxRow: Math.max(0, ...(shape?.rows.map((r) => r.number) ?? [])),
      rounds: (shape?.rows[0]?.kind ?? "round") === "round",
    };
  }, [result, query.color]);

  return (
    <div data-snapshot={status} style={{ position: "fixed", inset: 0, background: "var(--viewer-bg)" }}>
      {result && (
        <Viewer
          yarn={result.yarn}
          rowOf={rowOf}
          maxRow={maxRow}
          colorOf={colorOf}
          selected={null}
          onSelect={() => undefined}
          silhouette={false}
          view={query.view}
          rounds={rounds}
          material={query.material}
          showFps={false}
        />
      )}
    </div>
  );
}

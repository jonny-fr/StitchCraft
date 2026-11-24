import { Download, SlidersHorizontal } from "lucide-react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { StitchInfo, Stats } from "../api";
import { VIEWS } from "../snapshot";
import type { View } from "../viewer/Viewer";
import { Popover } from "./Popover";

interface Props {
  stats: Stats;
  selected: StitchInfo | undefined;
  view: View;
  onView(view: View): void;
  rowNumbers: number[];
  maxRow: number;
  onMaxRow(row: number): void;
  /** "up to here ≈ x min" for the slider, while a time estimate exists. */
  timeUpTo: string | null;
  /** The bottom right corner: the time chip. */
  corner: ReactNode;
  overlay: string | null;
  onOverlay(file: File | null): void;
  overlayOpacity: number;
  onOverlayOpacity(opacity: number): void;
  silhouette: boolean;
  onSilhouette(on: boolean): void;
  fuzz: boolean;
  onFuzz(on: boolean): void;
  onPng(): void;
  glbHref: string;
}

/**
 * Controls floating over the canvas: statistics and the picked stitch top left, tools and export top right,
 * views and the row slider bottom centre, the time chip (`corner`) bottom right.
 */
export function ViewerOverlay(props: Props) {
  const { t } = useTranslation();
  const { stats, selected: sel, view, rowNumbers, maxRow } = props;
  const last = rowNumbers.at(-1) ?? 1;

  return (
    <>
      <div className="chip info-chip">
        <p className="stats">
          {t("app.stats", {
            stitches: stats.stitches,
            size: stats.size_cm.join(" × "),
            yarn: stats.yarn_length_m,
            ms: Math.round(Object.values(stats.timings).reduce((a, b) => a + b, 0)),
          })}
        </p>
        {sel && <p>{t("app.selected", { id: sel.id, type: sel.type, row: sel.row, color: sel.color })}</p>}
      </div>

      <div className="viewer-actions">
        <Popover
          label={t("app.tools")}
          align="end"
          trigger={(p) => (
            <button {...p} className="icon" aria-label={t("app.tools")} title={t("app.tools")}>
              <SlidersHorizontal size={18} aria-hidden />
            </button>
          )}
        >
          {() => (
            <>
              <label className="button">
                {t("app.overlay")}
                <input type="file" accept="image/*" className="sr-only" onChange={(e) => props.onOverlay(e.target.files?.[0] ?? null)} />
              </label>
              {props.overlay && (
                <label className="field">
                  {t("app.overlayOpacity")}
                  <input type="range" min="0" max="1" step="0.05" value={props.overlayOpacity} onChange={(e) => props.onOverlayOpacity(Number(e.target.value))} />
                </label>
              )}
              <label className="field check">
                {t("app.silhouette")}
                <input type="checkbox" checked={props.silhouette} onChange={(e) => props.onSilhouette(e.target.checked)} />
              </label>
              <label className="field check">
                {t("app.fuzz")}
                <input type="checkbox" checked={props.fuzz} onChange={(e) => props.onFuzz(e.target.checked)} />
              </label>
            </>
          )}
        </Popover>
        <Popover
          label={t("app.export")}
          align="end"
          trigger={(p) => (
            <button {...p} className="icon" aria-label={t("app.export")} title={t("app.export")}>
              <Download size={18} aria-hidden />
            </button>
          )}
        >
          {(close) => (
            <div className="menu">
              <button onClick={() => (props.onPng(), close())}>{t("app.snapshot")}</button>
              <a className="button" href={props.glbHref} download="stitchcraft.glb">{t("app.exportGlb")}</a>
            </div>
          )}
        </Popover>
      </div>

      <div className="viewer-bottom">
        <div className="chip dock">
          <div className="segmented" role="group" aria-label={t("app.views")}>
            {VIEWS.map((v) => (
              <button key={v} aria-pressed={view === v} onClick={() => props.onView(v)}>{t(`app.${v}`)}</button>
            ))}
          </div>
          <div className="dock-slider">
            <label>
              {t("app.showUpToRow", { row: Math.min(maxRow, last) })}
              <input
                type="range"
                min={rowNumbers[0] ?? 1}
                max={last}
                value={Math.min(maxRow, last)}
                onChange={(e) => props.onMaxRow(Number(e.target.value))}
              />
            </label>
            {props.timeUpTo && <span className="time-up-to">{props.timeUpTo}</span>}
          </div>
        </div>
        {props.corner}
      </div>
    </>
  );
}

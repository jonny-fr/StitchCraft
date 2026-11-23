import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import type { PaletteColor, Params } from "../api";
import { paletteColors, type ColorState } from "../colors";
import { DIALECTS, dialectLabel } from "../dialects";
import { ParamsPanel } from "../params/ParamsPanel";
import { yarnClassOf } from "../params/yarnClasses";
import { ColorFields } from "./ColorFields";
import { Popover } from "./Popover";

interface Props {
  dialect: string;
  /** Dialect the server detected for `auto`, once known. */
  detected: string | undefined;
  onDialect(dialect: string): void;
  params: Params;
  onParams(params: Params): void;
  palette: PaletteColor[] | null;
  colors: ColorState;
  onColors(colors: ColorState): void;
}

function Segment({ title, value, align, children }: {
  title: string; value: ReactNode; align: "start" | "center" | "end"; children(close: () => void): ReactNode;
}) {
  return (
    <Popover
      label={title}
      align={align}
      trigger={(p) => (
        <button {...p} className="segment">
          <span className="segment-title">{title}</span>{" "}
          <span className="segment-value">{value}</span>
        </button>
      )}
    >
      {children}
    </Popover>
  );
}

/** Search-bar style pill in the header: dialect, yarn and colours, each opening its own popover. */
export function ContextPill({ dialect, detected, onDialect, params, onParams, palette, colors, onColors }: Props) {
  const { t } = useTranslation();
  const [more, setMore] = useState(false);
  const yarnClass = yarnClassOf(params.yarn_mm);
  const swatches = palette ? [...paletteColors(palette, colors.color, colors.picks).values()] : [colors.color];

  return (
    <div className="pill" role="group" aria-label={t("app.context")}>
      <Segment
        title={t("app.dialectShort")}
        value={dialect === "auto" ? `auto → ${detected ?? "–"}` : dialectLabel(dialect)}
        align="start"
      >
        {() => (
          <label className="field">
            {t("app.dialect")}
            <select value={dialect} onChange={(e) => onDialect(e.target.value)}>
              {DIALECTS.map((d) => (
                <option key={d.id} value={d.id}>{d.id === "auto" ? t("app.autoDialect", { dialect: detected ?? "–" }) : d.label}</option>
              ))}
            </select>
          </label>
        )}
      </Segment>
      <Segment
        title={t("app.yarn")}
        value={`${yarnClass ? t(`params.classes.${yarnClass.id}`) : `${params.yarn_mm} mm`} · ${t(`params.materials.${params.material}`)}`}
        align="center"
      >
        {() => <ParamsPanel params={params} onChange={onParams} more={more} onMore={setMore} />}
      </Segment>
      <Segment
        title={t("app.colorsShort")}
        value={swatches.map((hex, i) => <span key={i} className="swatch" style={{ background: hex }} />)}
        align="end"
      >
        {() => <ColorFields palette={palette} colors={colors} onChange={onColors} />}
      </Segment>
    </div>
  );
}

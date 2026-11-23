import { useId } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown } from "lucide-react";
import { MATERIALS, type Params } from "../api";
import { YARN_CLASSES, yarnClassOf } from "./yarnClasses";

interface Props {
  params: Params;
  onChange(params: Params): void;
  /** Whether the rarely changed fields below class and material are shown. */
  more: boolean;
  onMore(more: boolean): void;
}

const num = (v: string) => (v === "" ? null : Number(v));

/** Yarn parameters without the colour (that is the colour setting's job). */
export function ParamsPanel({ params, onChange, more, onMore }: Props) {
  const { t } = useTranslation();
  const moreId = useId();
  const set = <K extends keyof Params>(key: K, value: Params[K]) => onChange({ ...params, [key]: value });
  const yarnClass = yarnClassOf(params.yarn_mm);

  return (
    <fieldset className="params">
      <legend>{t("app.material")}</legend>
      <label>
        {t("params.yarnClass")}
        <select
          value={yarnClass?.id ?? "custom"}
          onChange={(e) => {
            const c = YARN_CLASSES.find((x) => x.id === e.target.value);
            if (c) onChange({ ...params, yarn_mm: c.yarn_mm, hook_mm: c.hook_mm });
          }}
        >
          {!yarnClass && <option value="custom">{t("params.custom")}</option>}
          {YARN_CLASSES.map((c) => (
            <option key={c.id} value={c.id}>
              {t("params.classOption", { name: t(`params.classes.${c.id}`), yarn: c.yarn_mm, hook: c.hook_mm })}
            </option>
          ))}
        </select>
      </label>
      <label>
        {t("params.material")}
        <select value={params.material} onChange={(e) => set("material", e.target.value as Params["material"])}>
          {MATERIALS.map((m) => <option key={m} value={m}>{t(`params.materials.${m}`)}</option>)}
        </select>
      </label>
      <button type="button" className="link more" aria-expanded={more} aria-controls={moreId} onClick={() => onMore(!more)}>
        {t("params.more")} <ChevronDown size={16} aria-hidden className="chevron" />
      </button>
      {more && (
        <div id={moreId} className="params-more">
          <label>{t("app.yarnMm")}<input type="number" step="0.1" min="0.4" max="14.9" value={params.yarn_mm} onChange={(e) => set("yarn_mm", Number(e.target.value))} /></label>
          <label>{t("app.hookMm")}<input type="number" step="0.25" min="0.75" max="24.75" value={params.hook_mm} onChange={(e) => set("hook_mm", Number(e.target.value))} /></label>
          <label>{t("app.gaugeStitches")}<input type="number" step="1" min="2" max="99" placeholder={t("params.estimated")} value={params.gauge_stitches ?? ""} onChange={(e) => set("gauge_stitches", num(e.target.value))} /></label>
          <label>{t("app.gaugeRows")}<input type="number" step="1" min="2" max="99" placeholder={t("params.estimated")} value={params.gauge_rows ?? ""} onChange={(e) => set("gauge_rows", num(e.target.value))} /></label>
          <label>{t("app.fill")} {params.fill.toFixed(1)}<input type="range" min="0" max="1" step="0.1" value={params.fill} onChange={(e) => set("fill", Number(e.target.value))} /></label>
          <label>
            {t("app.handedness")}
            <select value={params.handedness} onChange={(e) => set("handedness", e.target.value as Params["handedness"])}>
              <option value="right">{t("app.right")}</option>
              <option value="left">{t("app.left")}</option>
            </select>
          </label>
          <label>
            {t("params.sideOut")}
            <select value={params.right_side_out ? "right" : "wrong"} onChange={(e) => set("right_side_out", e.target.value === "right")}>
              <option value="right">{t("params.rightSide")}</option>
              <option value="wrong">{t("params.wrongSide")}</option>
            </select>
          </label>
        </div>
      )}
    </fieldset>
  );
}

import { useTranslation } from "react-i18next";
import type { PaletteColor } from "../api";
import { openColor, paletteColors, pickColor, type ColorState } from "../colors";

interface Props {
  /** The preview's palette; null before the first preview. */
  palette: PaletteColor[] | null;
  colors: ColorState;
  onChange(colors: ColorState): void;
}

/** The one colour setting: the yarn colour before a preview, one field per palette entry after it. */
export function ColorFields({ palette, colors, onChange }: Props) {
  const { t } = useTranslation();
  if (!palette) {
    return (
      <label className="field">
        {t("params.color")}
        <input type="color" value={colors.color} onChange={(e) => onChange({ ...colors, color: e.target.value })} />
      </label>
    );
  }
  const shown = paletteColors(palette, colors.color, colors.picks);
  const open = openColor(palette);
  return (
    <>
      {palette.map((c) => (
        <label key={c.ref} className="field" title={c.defined ? undefined : t("app.colorFallback")}>
          {c === open ? t("app.colorOpen", { ref: c.ref }) : t("app.colorOf", { ref: c.ref })}
          <input type="color" value={shown.get(c.ref)} onChange={(e) => onChange(pickColor(palette, c, e.target.value, colors))} />
        </label>
      ))}
    </>
  );
}

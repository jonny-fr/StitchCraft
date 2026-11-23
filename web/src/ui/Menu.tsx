import { CircleUserRound, Menu as MenuIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import { samples } from "../samples";
import { KEYS, save } from "../storage";
import { THEMES, type Theme } from "../theme";
import { Popover } from "./Popover";

interface Props {
  onSample(text: string): void;
  onImport(file: File): void;
  onExport(): void;
  theme: Theme;
  onTheme(theme: Theme): void;
}

/** The app menu at the top right: sample, .stitch.json import/export, UI language and theme. */
export function Menu({ onSample, onImport, onExport, theme, onTheme }: Props) {
  const { t, i18n } = useTranslation();
  return (
    <Popover
      label={t("app.menu")}
      align="end"
      trigger={(p) => (
        <button {...p} className="menu-button" aria-label={t("app.menu")}>
          <MenuIcon size={18} aria-hidden />
          <CircleUserRound size={28} aria-hidden />
        </button>
      )}
    >
      {(close) => (
        <div className="menu">
          <label className="field">
            {t("app.sample")}
            <select
              value=""
              onChange={(e) => {
                const s = samples.find((x) => x.id === e.target.value);
                if (s) (onSample(s.text), close());
              }}
            >
              <option value="">–</option>
              {samples.map((s) => <option key={s.id} value={s.id}>{s.id}</option>)}
            </select>
          </label>
          <label className="button">
            {t("app.importFile")}
            <input
              type="file"
              accept=".json,application/json"
              className="sr-only"
              onChange={(e) => {
                const f = e.target.files?.[0];
                e.target.value = "";
                if (f) (onImport(f), close());
              }}
            />
          </label>
          <button onClick={() => (onExport(), close())}>{t("app.exportFile")}</button>
          <hr />
          <label className="field">
            {t("app.uiLanguage")}
            <select value={i18n.language.slice(0, 2)} onChange={(e) => (void i18n.changeLanguage(e.target.value), save(KEYS.lang, e.target.value))}>
              <option value="de">Deutsch</option>
              <option value="en">English</option>
            </select>
          </label>
          <label className="field">
            {t("app.theme")}
            <select value={theme} onChange={(e) => onTheme(e.target.value as Theme)}>
              {THEMES.map((th) => <option key={th} value={th}>{t(`app.themes.${th}`)}</option>)}
            </select>
          </label>
        </div>
      )}
    </Popover>
  );
}

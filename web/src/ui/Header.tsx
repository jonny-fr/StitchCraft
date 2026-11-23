import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

/** Top bar: wordmark left, the context pill in the middle, the menu right. */
export function Header({ pill, menu }: { pill: ReactNode; menu: ReactNode }) {
  const { t } = useTranslation();
  return (
    <header className="topbar">
      <h1 className="wordmark">{t("app.title")}</h1>
      {pill}
      {menu}
    </header>
  );
}

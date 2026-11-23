import { useEffect, useState } from "react";

export const THEMES = ["dark", "light", "system"] as const;
export type Theme = (typeof THEMES)[number];

const PREFERS_DARK = "(prefers-color-scheme: dark)";

/** app.css picks the token set from `data-theme` on <html>. */
export function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme;
}

/** Whether the theme ends up dark; `system` follows the OS setting as it changes. */
export function useDarkScheme(theme: Theme): boolean {
  const [systemDark, setSystemDark] = useState(() => window.matchMedia(PREFERS_DARK).matches);
  useEffect(() => {
    const mq = window.matchMedia(PREFERS_DARK);
    const on = () => setSystemDark(mq.matches);
    mq.addEventListener("change", on);
    return () => mq.removeEventListener("change", on);
  }, []);
  return theme === "system" ? systemDark : theme === "dark";
}

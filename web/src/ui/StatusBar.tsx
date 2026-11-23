import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { CircleCheck, CircleAlert, ChevronDown, TriangleAlert } from "lucide-react";
import type { Diagnostic, Validation } from "../api";

interface Props {
  validation: Validation | null;
  message(d: Diagnostic): string;
  onPick(d: Diagnostic): void;
}

const SEVERITIES = ["error", "warning", "info"] as const;
const ICON = { ok: CircleCheck, error: CircleAlert, warning: TriangleAlert };

/** One line under the editor summing up the lint; it unfolds into the diagnostics and the stitch counts per row. */
export function StatusBar({ validation, message, onPick }: Props) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const id = useId();
  const diags = validation?.diagnostics ?? [];
  const count = (s: (typeof SEVERITIES)[number]) => diags.filter((d) => d.severity === s).length;
  // notes (ignored prose) are no problems: they only add to the summary
  const worst = (["error", "warning"] as const).find((s) => count(s) > 0) ?? "ok";
  const parts = SEVERITIES.filter((s) => count(s) > 0).map((s) => t(`app.status.${s}`, { count: count(s) }));
  const summary = !validation ? t("app.status.checking") : [...(worst === "ok" ? [t("app.noDiagnostics")] : []), ...parts].join(" · ");
  const Icon = ICON[worst];

  return (
    <div className="status card">
      <button className={`status-bar ${worst}`} aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)}>
        <Icon size={18} aria-hidden />
        {summary}
        <ChevronDown size={18} aria-hidden className="chevron" />
      </button>
      {open && (
        <div id={id} className="status-details">
          {diags.length > 0 && (
            <ul className="diagnostics">
              {diags.map((d, i) => (
                <li key={i} className={d.severity}>
                  <button className="link" onClick={() => onPick(d)}>{message(d)}</button>
                </li>
              ))}
            </ul>
          )}
          <h2>{t("app.rowCounts")}</h2>
          <table className="counts">
            <tbody>
              {validation?.rows.map((r) => (
                <tr key={r.number} className={r.expected !== null && r.expected !== r.actual ? "bad" : ""}>
                  <td>{t("app.row", { number: r.number })}</td>
                  <td>{r.actual}</td>
                  <td>{r.expected ?? ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

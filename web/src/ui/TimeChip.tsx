import { Timer } from "lucide-react";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { PACES, type TimeEstimate } from "../api";
import { formatDuration, formatRange, stitchesPerMinuteValid, type PaceSetting } from "../time";
import { Popover } from "./Popover";

interface Props {
  estimate: TimeEstimate | null | undefined;
  pace: PaceSetting;
  onPace(pace: PaceSetting): void;
  /** Placement: `viewer-time` (bottom right of the viewer) or `editor-time` (under the editor, small screens). */
  className: string;
}

/** The estimated crochet time as a chip; its popover holds the pace, an own pace and the time per round/row. */
export function TimeChip({ estimate, pace, onPace, className }: Props) {
  const { t } = useTranslation();
  if (!estimate) return null;
  const range = formatRange(t, estimate.seconds_low, estimate.seconds_high);
  return (
    <Popover
      label={t("time.label")}
      align="end"
      className={`time ${className}`}
      trigger={(p) => (
        <button {...p} className="chip time-chip" title={t("time.note")}>
          <Timer size={16} aria-hidden />
          <span className="sr-only">{t("time.label")}</span>{" "}
          {range}
        </button>
      )}
    >
      {() => <TimePanel estimate={estimate} range={range} pace={pace} onPace={onPace} />}
    </Popover>
  );
}

function TimePanel({ estimate, range, pace, onPace }: { estimate: TimeEstimate; range: string; pace: PaceSetting; onPace(p: PaceSetting): void }) {
  const { t } = useTranslation();
  // the field keeps what is typed; only a valid number becomes the own pace
  const [draft, setDraft] = useState(pace.stitchesPerMinute === null ? "" : String(pace.stitchesPerMinute));
  const own = pace.stitchesPerMinute !== null;

  return (
    <>
      <h2>{t("time.label")} {range}</h2>
      <div className="segmented" role="group" aria-label={t("time.pace")}>
        {PACES.map((p) => (
          <button key={p} aria-pressed={!own && pace.pace === p} onClick={() => (setDraft(""), onPace({ pace: p, stitchesPerMinute: null }))}>
            {t(`time.paces.${p}`)}
          </button>
        ))}
      </div>
      <label className="field">
        {t("time.ownPace")}
        <input
          type="number"
          min="1"
          max="200"
          step="1"
          value={draft}
          onChange={(e) => {
            setDraft(e.target.value);
            const v = e.target.value === "" ? null : Number(e.target.value);
            if (v === null || stitchesPerMinuteValid(v)) onPace({ ...pace, stitchesPerMinute: v });
          }}
        />
      </label>
      <p className="hint">{t("time.ownPaceHint")}</p>
      <h2>{t("time.perRow")}</h2>
      <div className="time-rows" role="region" aria-label={t("time.perRow")} tabIndex={0}>
        <table className="counts">
          <tbody>
            {estimate.per_row.map((r) => (
              <tr key={r.number}>
                <td>{t("app.row", { number: r.number })}</td>
                <td>{formatDuration(t, r.seconds)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="hint">{t("time.note")}</p>
    </>
  );
}

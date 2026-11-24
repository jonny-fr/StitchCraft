import type { TFunction } from "i18next";
import { PACES, type Pace, type TimeEstimate } from "./api";

/** The crochet pace for the time estimate; an own pace (sc per minute) replaces the preset. */
export interface PaceSetting { pace: Pace; stitchesPerMinute: number | null }
export const defaultPace: PaceSetting = { pace: "geuebt", stitchesPerMinute: null };

/** Mirrors the server's ValidateIn bound for stitches_per_minute. */
export const stitchesPerMinuteValid = (v: unknown): v is number => typeof v === "number" && Number.isFinite(v) && v > 0 && v <= 200;

/** A stored or imported pace; each invalid part falls back to the default. */
export function sanitizePace(raw: unknown): PaceSetting {
  if (typeof raw !== "object" || raw === null || Array.isArray(raw)) return defaultPace;
  const { pace, stitchesPerMinute } = raw as Record<string, unknown>;
  return {
    pace: PACES.includes(pace as Pace) ? (pace as Pace) : defaultPace.pace,
    stitchesPerMinute: stitchesPerMinuteValid(stitchesPerMinute) ? stitchesPerMinute : null,
  };
}

type Unit = "min" | "hour";

/** Minutes below an hour (whole minutes below 10, then steps of 5), else hours in steps of ½. */
function unitFor(seconds: number): Unit {
  return seconds < 3600 ? "min" : "hour";
}

function amount(t: TFunction, seconds: number, unit: Unit): string {
  if (unit === "min") {
    const minutes = seconds / 60;
    const step = minutes < 10 ? 1 : 5;
    return String(Math.max(step, Math.round(minutes / step) * step));
  }
  const halves = Math.max(1, Math.round(seconds / 1800));
  const whole = Math.floor(halves / 2);
  return `${whole || ""}${halves % 2 ? t("time.half") : ""}`;
}

/** "≈ 25 min", "≈ 2½ h"; under a minute "< 1 min". */
export function formatDuration(t: TFunction, seconds: number): string {
  if (seconds < 60) return t("time.lessThanMinute");
  const unit = unitFor(seconds);
  return t(`time.${unit}`, { value: amount(t, seconds, unit) });
}

/** "≈ 15–25 min", "≈ 2½–3 h"; the larger end picks the unit, equal ends give one value. */
export function formatRange(t: TFunction, low: number, high: number): string {
  if (high < 60) return t("time.lessThanMinute");
  const unit = unitFor(high);
  const [a, b] = [amount(t, low, unit), amount(t, high, unit)];
  return a === b ? t(`time.${unit}`, { value: b }) : t(`time.${unit}Range`, { low: a, high: b });
}

/** Middle of the estimate from the first round/row up to and including `row`. */
export function secondsUpTo(estimate: TimeEstimate, row: number): number {
  return estimate.per_row.filter((r) => r.number <= row).reduce((sum, r) => sum + r.seconds, 0);
}

// How replan findings read on screen. One table per backend enum, keyed by
// the full union, so a code the backend adds cannot compile unlabelled.

import type { AlertCode, AlertSeverity } from "./types";

export const ALERT_CODES: Readonly<
  Record<AlertCode, { readonly label: string }>
> = {
  ENERGY_BELOW_RESERVE: { label: "Energy below reserve" },
  ENERGY_NEAR_RESERVE: { label: "Energy near reserve" },
  WIND_EXCEEDS_LIMIT: { label: "Wind over airframe limit" },
  SOC_STALE: { label: "Telemetry too old" },
  WEATHER_DEGRADED: { label: "Wind not reported" },
  PAYLOAD_MISMATCH: { label: "Payload differs from brief" },
};

export type FindingTone = "stale" | "caution" | "critical";

/** No finding is green: an alert means something could not be confirmed. */
export const SEVERITY: Readonly<
  Record<AlertSeverity, { readonly label: string; readonly tone: FindingTone }>
> = {
  info: { label: "Info", tone: "stale" },
  watch: { label: "Watch", tone: "caution" },
  warning: { label: "Warning", tone: "caution" },
  abort: { label: "Abort", tone: "critical" },
};

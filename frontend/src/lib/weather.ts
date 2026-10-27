// How each weather provenance state looks. Keyed by the full WeatherSource
// union, so a state the backend adds cannot compile without a rendering here.

import type { WeatherSource } from "./types";

export type SourceTone = "ok" | "stale" | "caution" | "critical";

export interface SourceTreatment {
  readonly label: string;
  readonly tone: SourceTone;
  /** Mirrors the backend's OPERATIONAL_WEATHER set. */
  readonly operational: boolean;
  /** A reading that was not fetched now draws a dashed edge. */
  readonly dashed: boolean;
  readonly detail: string;
}

export const SOURCE_TREATMENT: Readonly<
  Record<WeatherSource, SourceTreatment>
> = {
  live: {
    label: "Live",
    tone: "ok",
    operational: true,
    dashed: false,
    detail: "Fetched now, parsed and complete.",
  },
  cached_fresh: {
    label: "Cached, fresh",
    tone: "ok",
    operational: true,
    dashed: true,
    detail: "A recent reading, still inside its freshness window.",
  },
  cached_stale: {
    label: "Cached, stale",
    tone: "stale",
    operational: false,
    dashed: true,
    detail: "Past its freshness window; the live fetch failed.",
  },
  fallback: {
    label: "Fallback",
    tone: "caution",
    operational: false,
    dashed: false,
    detail: "Defaults: the provider could not be reached.",
  },
  error: {
    label: "Provider error",
    tone: "critical",
    operational: false,
    dashed: false,
    detail: "Defaults: the provider's answer was unusable.",
  },
  fixture: {
    label: "Demo fixture",
    tone: "caution",
    operational: false,
    dashed: true,
    detail: "A fixed demo reading, not observed weather.",
  },
};

const TONE_CLASS: Readonly<Record<SourceTone, string>> = {
  ok: "border-ok bg-ok-tint text-ok",
  stale: "border-stale bg-stale-tint text-stale",
  caution: "border-caution bg-caution-tint text-caution",
  critical: "border-critical bg-critical-tint text-critical",
};

export function sourceClass(source: WeatherSource): string {
  const treatment = SOURCE_TREATMENT[source];
  const edge = treatment.dashed ? "border-dashed" : "border-solid";
  return `${TONE_CLASS[treatment.tone]} ${edge}`;
}

import type { JSX } from "react";

import type { WeatherSource } from "@/lib/types";
import { SOURCE_TREATMENT, sourceClass } from "@/lib/weather";

/** Where the weather came from, in a treatment no other state shares (#93). */
export function WeatherSourceChip({
  source,
}: {
  readonly source: WeatherSource;
}): JSX.Element {
  const treatment = SOURCE_TREATMENT[source];
  const grade = treatment.operational ? "operational" : "not operational";
  return (
    <span className="inline-flex items-baseline gap-2">
      <span
        className={`rounded-sm border px-1 text-xs font-semibold uppercase tracking-label ${sourceClass(source)}`}
        title={`${source}: ${treatment.detail}`}
      >
        {treatment.label}
      </span>
      <span className="text-sm text-fg-muted">{grade}</span>
    </span>
  );
}

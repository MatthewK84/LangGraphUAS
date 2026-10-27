import type { JSX } from "react";

import type { AdvisoryNotice } from "@/lib/advisory";
import { SOURCE_TREATMENT } from "@/lib/weather";

function Fact({
  label,
  value,
}: {
  readonly label: string;
  readonly value: string;
}): JSX.Element {
  return (
    <span className="flex items-baseline gap-1">
      <span className="text-fg-muted">{label}</span>
      <span className="font-mono text-fg">{value}</span>
    </span>
  );
}

function alertCount(count: number): string {
  return count === 1 ? "1 alert" : `${String(count)} alerts`;
}

/**
 * Sits in the shell between the top bar and the panels, outside every scroll
 * region, so no amount of scrolling the figures takes it off screen.
 */
export function AdvisoryBanner({
  notice,
}: {
  readonly notice: AdvisoryNotice | null;
}): JSX.Element | null {
  if (notice === null) {
    return null;
  }
  const replanAlerts = notice.replanAlerts ?? 0;
  return (
    <section
      aria-label="Advisory: not a clearance"
      className="flex h-header shrink-0 items-center justify-between gap-4 border-b border-l-4 border-b-line border-l-caution bg-caution-tint px-3 text-sm"
    >
      <div className="flex items-baseline gap-4">
        <span className="font-semibold uppercase tracking-label text-caution">
          Advisory, not a clearance
        </span>
        <Fact label="Mode" value={notice.mode} />
        <Fact
          label="Weather"
          value={
            notice.weatherSource === null
              ? "none"
              : SOURCE_TREATMENT[notice.weatherSource].label
          }
        />
        {replanAlerts > 0 && (
          <Fact label="Replan" value={alertCount(replanAlerts)} />
        )}
      </div>
      <span className="text-fg-secondary">
        Planning support only. Do not launch on this plan.
      </span>
    </section>
  );
}

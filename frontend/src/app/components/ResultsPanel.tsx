import type { JSX } from "react";

import type {
  Assessment,
  Calculations,
  FigureProvenance,
  PlanResult,
  WeatherReading,
} from "@/lib/types";

import { FigureTable } from "./FigureTable";
import type { FigureRow } from "./FigureTable";
import { StatusBanner } from "./StatusBanner";

interface ResultsPanelProps {
  readonly loading: boolean;
  readonly error: string | null;
  readonly result: PlanResult | null;
}

function Notice({
  title,
  items,
  tone,
  mono = false,
}: {
  readonly title: string;
  readonly items: readonly string[];
  readonly tone: "caution" | "neutral";
  readonly mono?: boolean;
}): JSX.Element {
  const border =
    tone === "caution"
      ? "border-l-caution bg-caution-tint"
      : "border-l-line-strong";
  return (
    <div
      className={`border-b border-l-2 border-b-line px-3 py-2 ${border}`}
      role={tone === "caution" ? "alert" : "note"}
    >
      <span
        className={`section-label ${tone === "caution" ? "text-caution" : ""}`}
      >
        {title}
      </span>
      <ul
        className={`mt-1 list-inside list-disc space-y-0.5 text-md text-fg-secondary ${mono ? "font-mono text-sm" : ""}`}
      >
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </div>
  );
}

function BlockerList({
  assessment,
}: {
  readonly assessment: Assessment;
}): JSX.Element | null {
  if (assessment.mode === "operational" || assessment.blockers.length === 0) {
    return null;
  }
  return (
    <Notice
      title="Why this plan is advisory"
      items={assessment.blockers}
      tone="neutral"
      mono
    />
  );
}

function weatherRows(weather: WeatherReading): readonly FigureRow[] {
  return [
    {
      label: "Source",
      value: weather.source === "live" ? "Live feed" : "Fallback defaults",
      unit: "",
    },
    { label: "Conditions", value: weather.conditions, unit: "" },
    { label: "Air temperature", value: weather.temperature_c, unit: "°C" },
    { label: "Wind", value: weather.wind_speed_mps, unit: "m/s" },
    { label: "Gust", value: weather.wind_gust_mps, unit: "m/s" },
  ];
}

function performanceRows(calc: Calculations): readonly FigureRow[] {
  return [
    {
      label: "Density altitude",
      value: calc.density_altitude_m,
      unit: "m MSL",
    },
    {
      label: "Air density",
      value: Math.round(calc.air_density_ratio * 100),
      unit: "%",
      note: "of sea level",
    },
    { label: "All-up mass", value: calc.all_up_mass_kg, unit: "kg" },
    {
      label: "Hover power (corrected)",
      value: calc.effective_hover_power_w,
      unit: "W",
      path: "effective_hover_power_w",
    },
    {
      label: "Ground speed (worst headwind)",
      value: calc.ground_speed_mps,
      unit: "m/s",
    },
    { label: "Payload margin", value: calc.payload_margin_kg, unit: "kg" },
  ];
}

function energyRows(calc: Calculations): readonly FigureRow[] {
  const parts = calc.energy_breakdown;
  const battery = calc.battery_check;
  const derated = battery.temperature_factor < 1;
  const wh = (label: string, value: number, path: string): FigureRow => ({
    label,
    value,
    unit: "Wh",
    path,
  });
  return [
    wh("Climb", parts.climb_wh, "energy_breakdown.climb_wh"),
    wh("Cruise", parts.cruise_wh, "energy_breakdown.cruise_wh"),
    wh("Hover", parts.hover_wh, "energy_breakdown.hover_wh"),
    wh("Descent", parts.descent_wh, "energy_breakdown.descent_wh"),
    wh("Energy required", calc.energy_required_wh, "energy_required_wh"),
    {
      ...wh(
        "Usable capacity",
        battery.usable_capacity_wh,
        "battery_check.usable_capacity_wh",
      ),
      ...(derated
        ? {
            label: `Usable capacity (cold-derated to ${String(Math.round(battery.temperature_factor * 100))}%)`,
          }
        : {}),
    },
    {
      ...wh("Margin", battery.margin_wh, "battery_check.margin_wh"),
      tone: battery.margin_wh >= 0 ? "ok" : "critical",
    },
  ];
}

function Figures({ result }: { readonly result: PlanResult }): JSX.Element {
  const provenance: FigureProvenance = result.provenance;
  const calc = result.calculations;
  return (
    <div className="grid grid-cols-1 border-b border-line wide:grid-cols-2">
      <div className="border-line wide:border-r">
        {result.weather !== null && (
          <FigureTable
            title="Weather"
            rows={weatherRows(result.weather)}
            provenance={provenance}
          />
        )}
        {calc !== null && (
          <FigureTable
            title="Performance"
            rows={performanceRows(calc)}
            provenance={provenance}
          />
        )}
      </div>
      <div>
        {calc !== null && (
          <FigureTable
            title="Energy budget"
            rows={energyRows(calc)}
            provenance={provenance}
          />
        )}
      </div>
    </div>
  );
}

function Skeleton(): JSX.Element {
  const bars = ["w-2/5", "w-1/3", "w-1/2", "w-1/4", "w-2/5", "w-1/3"];
  return (
    <div aria-busy="true">
      <div className="h-strip border-b border-line bg-raised" />
      <p className="px-3 py-2 text-sm text-fg-muted">
        Running physics simulations and prompting the AI copilot...
      </p>
      <div className="grid grid-cols-2">
        {[0, 1].map((column) => (
          <div key={column} className="space-y-2 px-3 py-2">
            {bars.map((width, index) => (
              <div
                key={String(index)}
                className={`h-3 rounded-sm bg-raised ${width}`}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

/**
 * The brief is written after the signature (ADR-004), so before it there is
 * nothing to show: what the operator signs is the calculator's alone. Even a
 * report that arrives early is withheld until the plan is no longer awaiting.
 */
function Brief({ result }: { readonly result: PlanResult }): JSX.Element {
  if (result.awaiting_ack) {
    return (
      <p className="px-3 py-3 text-sm text-fg-muted">
        No brief yet. It is written after the assessment is signed.
      </p>
    );
  }
  return (
    <section className="px-3 py-3">
      <h3 className="section-label mb-2">AI Safety Officer Report</h3>
      <div className="max-w-prose whitespace-pre-wrap text-md leading-normal text-fg-secondary">
        {result.report}
      </div>
    </section>
  );
}

export function ResultsPanel(props: ResultsPanelProps): JSX.Element {
  const { loading, error, result } = props;
  if (error !== null) {
    return (
      <div
        className="m-3 border-l-2 border-critical bg-critical-tint px-3 py-2 text-md text-fg"
        role="alert"
      >
        {error}
      </div>
    );
  }
  if (loading) {
    return <Skeleton />;
  }
  if (result === null) {
    return (
      <div className="flex h-full items-center justify-center p-8 text-center text-md text-fg-muted">
        No plan yet. Set the aircraft, payload, profile and location, then
        analyze flight feasibility.
      </div>
    );
  }
  return (
    <div>
      <StatusBanner result={result} />
      {result.assessment !== null && (
        <BlockerList assessment={result.assessment} />
      )}
      {result.warnings.length > 0 && (
        <Notice
          title="Degraded inputs"
          items={result.warnings}
          tone="caution"
        />
      )}
      <Figures result={result} />
      <Brief result={result} />
    </div>
  );
}

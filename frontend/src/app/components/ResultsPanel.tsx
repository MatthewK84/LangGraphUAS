import type { JSX } from "react";

import type { Calculations, PlanResult, WeatherReading } from "@/lib/types";

interface ResultsPanelProps {
  readonly loading: boolean;
  readonly error: string | null;
  readonly result: PlanResult | null;
}

function StatusBanner({ result }: { readonly result: PlanResult }): JSX.Element {
  const tone = result.is_viable
    ? "bg-emerald-950/40 border-emerald-800 text-emerald-400"
    : "bg-rose-950/40 border-rose-800 text-rose-400";
  const label = result.is_viable ? "CLEAR TO LAUNCH (GO)" : "MISSION DENIED (NO-GO)";
  return (
    <div className={`p-4 rounded-xl border flex items-center justify-between shadow-md ${tone}`}>
      <div>
        <span className="font-bold text-lg tracking-wide">FLIGHT DISPATCH STATUS: {label}</span>
        <p className="text-xs mt-1 opacity-75 font-mono">Memory Thread ID: {result.thread_id}</p>
      </div>
    </div>
  );
}

function TelemetryCard({ weather }: { readonly weather: WeatherReading }): JSX.Element {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl p-4 shadow-sm">
      <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
        Live Environmental Telemetry
      </span>
      <div className="mt-2 space-y-1 text-sm">
        <p>Conditions: <span className="text-white font-medium">{weather.conditions}</span></p>
        <p>Air Temperature: <span className="text-white font-medium">{weather.temperature_c}&deg;C</span></p>
        <p>Wind Velocity: <span className="text-white font-medium">{weather.wind_speed_mps} m/s</span></p>
      </div>
    </div>
  );
}

function PerformanceCard({ calculations }: { readonly calculations: Calculations }): JSX.Element {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl p-4 shadow-sm">
      <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
        Aero-Engineering Performance
      </span>
      <div className="mt-2 space-y-1 text-sm">
        <p>Density Altitude: <span className="text-white font-medium">{calculations.density_altitude_m} m</span></p>
        <p>Energy Budget: <span className="text-white font-medium">{calculations.energy_required_wh} Wh</span></p>
        <p>Payload Margin: <span className="text-white font-medium">{calculations.payload_margin_kg} kg</span></p>
      </div>
    </div>
  );
}

export function ResultsPanel(props: ResultsPanelProps): JSX.Element {
  const { loading, error, result } = props;
  if (error !== null) {
    return (
      <div className="bg-rose-950/40 border border-rose-800 rounded-xl p-8 text-rose-300" role="alert">
        {error}
      </div>
    );
  }
  if (loading) {
    return (
      <div className="bg-slate-800 border border-slate-700 rounded-xl p-12 text-center text-slate-400 animate-pulse">
        Running physics simulations and prompting the AI copilot...
      </div>
    );
  }
  if (result === null) {
    return (
      <div className="bg-slate-800 border border-dashed border-slate-700 rounded-xl p-12 text-center text-slate-500">
        Configure mission objectives and location metrics to view dispatch parameters.
      </div>
    );
  }
  return (
    <div className="space-y-6">
      <StatusBanner result={result} />
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {result.weather !== null && <TelemetryCard weather={result.weather} />}
        {result.calculations !== null && <PerformanceCard calculations={result.calculations} />}
      </div>
      <div className="bg-slate-800 border border-slate-700 rounded-xl p-6 shadow-xl">
        <h3 className="text-lg font-semibold border-b border-slate-700 pb-2 text-white mb-4">
          AI Safety Officer Report
        </h3>
        <div className="max-w-none text-slate-300 text-sm leading-relaxed whitespace-pre-wrap">
          {result.report}
        </div>
      </div>
    </div>
  );
}

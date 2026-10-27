// Shared data-shape definitions for the mission planner UI.
// Every structure crossing a function boundary is declared here (Principle 8).

export interface SafetyFlags {
  readonly battery_viable: boolean;
  readonly payload_within_limits: boolean;
  readonly wind_within_limits: boolean;
  readonly gust_within_limits: boolean;
  readonly temperature_within_limits: boolean;
  /** Ambient is at or above the pack's documented takeoff minimum, where one exists. */
  readonly pack_temp_within_takeoff_limits: boolean;
  readonly cruise_achievable: boolean;
}

/** Mirrors the backend `WeatherSource`; only live and cached_fresh can be operational. */
export type WeatherSource =
  "live" | "cached_fresh" | "cached_stale" | "fallback" | "error" | "fixture";

export interface WeatherReading {
  readonly temperature_c: number;
  readonly wind_speed_mps: number;
  readonly wind_gust_mps: number;
  readonly wind_direction: number;
  readonly humidity_percent: number;
  readonly conditions: string;
  readonly source: WeatherSource;
}

export interface EnergyBreakdown {
  readonly climb_wh: number;
  readonly cruise_wh: number;
  readonly hover_wh: number;
  readonly descent_wh: number;
  readonly total_wh: number;
}

export interface BatteryCheck {
  readonly energy_required_wh: number;
  readonly usable_capacity_wh: number;
  readonly margin_wh: number;
  readonly reserve_percent: number;
  readonly temperature_factor: number;
  readonly is_viable: boolean;
}

export interface Calculations {
  readonly density_altitude_m: number;
  readonly air_density_ratio: number;
  readonly energy_required_wh: number;
  readonly energy_breakdown: EnergyBreakdown;
  readonly payload_margin_kg: number;
  readonly all_up_mass_kg: number;
  readonly ground_speed_mps: number;
  readonly effective_hover_power_w: number;
  readonly battery_check: BatteryCheck;
  readonly safety_flags: SafetyFlags;
}

/**
 * What one W or Wh figure in `Calculations` rests on: the weakest source and
 * lowest confidence among the reference fields it was computed from.
 * `operational_grade` is the backend gate's own rule, so it is not repeated here.
 */
export interface NumberProvenance {
  readonly source:
    | "datasheet"
    | "flight_log"
    | "secondary"
    | "derived"
    | "estimate"
    | "unknown";
  readonly confidence: "low" | "medium" | "high";
  readonly operational_grade: boolean;
  readonly inputs: readonly string[];
}

/** Keyed by the figure's dotted path in `Calculations`. */
export type FigureProvenance = Readonly<Record<string, NumberProvenance>>;

export type Decision = "go" | "no_go" | "insufficient_data";

export type AssessmentMode = "advisory" | "operational";

/**
 * The sealed decision. Produced by the backend calculator, never by the model.
 * `mode` is what the gate granted, which may be less than was requested.
 */
export interface Assessment {
  readonly decision: Decision;
  readonly reasons: readonly string[];
  readonly mode: AssessmentMode;
  readonly blockers: readonly string[];
  readonly inputs_hash: string;
  readonly calculator_version: string;
}

export type AckAction = "confirm" | "edit" | "abort";

export interface AckRequest {
  readonly action: AckAction;
  readonly actor: string;
  /** The assessment the operator was shown. Refused if it has since changed. */
  readonly inputs_hash?: string;
}

export interface PlanResult {
  readonly is_viable: boolean;
  readonly assessment: Assessment | null;
  /** True while the run is paused for a signature. No brief exists yet. */
  readonly awaiting_ack: boolean;
  readonly aborted: boolean;
  readonly weather: WeatherReading | null;
  readonly calculations: Calculations | null;
  readonly provenance: FigureProvenance;
  readonly report: string;
  readonly thread_id: string;
  readonly degraded: boolean;
  readonly warnings: readonly string[];
}

export type AlertSeverity = "info" | "watch" | "warning" | "abort";

export type RecommendedAction =
  "continue" | "land_soon" | "land_now" | "advisory_only";

export type AlertCode =
  | "ENERGY_BELOW_RESERVE"
  | "ENERGY_NEAR_RESERVE"
  | "WIND_EXCEEDS_LIMIT"
  | "SOC_STALE"
  | "WEATHER_DEGRADED"
  | "PAYLOAD_MISMATCH";

/** One finding from comparing the briefed plan against live telemetry. */
export interface ReplanAlert {
  readonly severity: AlertSeverity;
  readonly code: AlertCode;
  readonly message: string;
  readonly briefed: Readonly<Record<string, unknown>>;
  readonly live: Readonly<Record<string, unknown>>;
  readonly delta: Readonly<Record<string, unknown>>;
  readonly recommended_action: RecommendedAction;
}

export interface LiveEnergy {
  readonly available_wh: number;
  readonly reserve_wh: number;
  readonly required_wh: number;
  readonly residual_wh: number;
  readonly temperature_factor: number;
}

/**
 * A replan against live telemetry. `operational_ok` is false whenever any
 * alert fired, including a watch: an unconfirmed replan is advice.
 */
export interface ReplanResult {
  readonly thread_id: string;
  readonly parent_thread_id: string;
  readonly severity: AlertSeverity;
  readonly recommended_action: RecommendedAction;
  readonly operational_ok: boolean;
  readonly live_energy: LiveEnergy | null;
  readonly briefed_margin_wh: number | null;
  readonly snapshot_age_s: number;
  readonly alerts: readonly ReplanAlert[];
}

/**
 * One live report sent for a replan. State of charge travels as a fraction,
 * as the backend takes it; the form converts from the percent typed.
 */
export interface TelemetrySnapshotRequest {
  readonly thread_id: string;
  /** ISO 8601, UTC. */
  readonly ts: string;
  readonly latitude: number;
  readonly longitude: number;
  readonly alt_m: number;
  readonly soc_fraction: number;
  readonly remaining_leg_m: number;
  readonly remaining_hover_s: number;
  readonly oat_c: number;
  /** Null when the aircraft reports none; the backend then raises a watch. */
  readonly wind_mps: number | null;
  readonly payload_attached: boolean;
}

export interface MissionParams {
  readonly distance_m: number;
  readonly hover_time_s: number;
  readonly target_altitude_m: number;
  readonly elevation_m: number;
  readonly latitude: number;
  readonly longitude: number;
}

export interface MissionRequest {
  readonly aircraft_id: string;
  readonly payload_id: string;
  readonly mission_params: MissionParams;
  readonly thread_id: string | null;
}

// Discriminated result type so callers handle success and failure explicitly.
export type ApiResult<T> =
  | { readonly ok: true; readonly data: T }
  | { readonly ok: false; readonly error: string };

export interface AircraftSummary {
  readonly id: string;
  readonly name: string;
  readonly max_payload_kg: number;
  readonly battery_wh: number;
  readonly max_wind_mps: number;
  readonly max_temp_c: number;
}

export interface PayloadSummary {
  readonly id: string;
  readonly name: string;
  readonly weight_kg: number;
  readonly power_draw_w: number;
}

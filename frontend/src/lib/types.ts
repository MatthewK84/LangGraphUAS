// Shared data-shape definitions for the mission planner UI.
// Every structure crossing a function boundary is declared here (Principle 8).

export interface SafetyFlags {
  readonly battery_viable: boolean;
  readonly payload_within_limits: boolean;
  readonly wind_within_limits: boolean;
  readonly gust_within_limits: boolean;
  readonly temperature_within_limits: boolean;
  readonly cruise_achievable: boolean;
}

export type WeatherSource = "live" | "fallback";

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

export interface PlanResult {
  readonly is_viable: boolean;
  readonly weather: WeatherReading | null;
  readonly calculations: Calculations | null;
  readonly report: string;
  readonly thread_id: string;
  readonly degraded: boolean;
  readonly warnings: readonly string[];
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

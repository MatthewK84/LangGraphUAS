// Plan responses as the backend sends them, for component tests and the local
// screenshot loop. Figures are taken from a real demo-mode run, so they carry
// the calculator's own precision rather than round placeholders.
import type { FigureProvenance, PlanResult } from "@/lib/types";

const ESTIMATE = {
  source: "estimate",
  confidence: "low",
  operational_grade: false,
  inputs: ["hover_power_w", "cruise_power_w"],
} as const;

export const PROVENANCE: FigureProvenance = {
  effective_hover_power_w: ESTIMATE,
  energy_required_wh: ESTIMATE,
  "energy_breakdown.climb_wh": ESTIMATE,
  "energy_breakdown.cruise_wh": ESTIMATE,
  "energy_breakdown.hover_wh": ESTIMATE,
  "energy_breakdown.descent_wh": ESTIMATE,
  "battery_check.usable_capacity_wh": {
    source: "datasheet",
    confidence: "high",
    operational_grade: true,
    inputs: ["battery_wh"],
  },
  "battery_check.margin_wh": ESTIMATE,
};

export const ADVISORY_PLAN: PlanResult = {
  is_viable: true,
  assessment: {
    decision: "go",
    reasons: ["Energy margin 41.7 Wh above the 20% reserve"],
    mode: "advisory",
    blockers: [
      "weather source is fixture, not live or cached_fresh",
      "hover_power_w is estimate (low confidence)",
    ],
    inputs_hash:
      "9f3c27a1d0b84e6f5a2c9e71b3d4f6a8c0e2b4d6f8a1c3e5b7d9f0a2c4e6b8d1",
    calculator_version: "2.4.1",
  },
  awaiting_ack: true,
  aborted: false,
  weather: {
    temperature_c: 18.3,
    wind_speed_mps: 4.6,
    wind_gust_mps: 7.2,
    wind_direction: 245,
    humidity_percent: 61,
    conditions: "Scattered clouds",
    source: "fallback",
  },
  calculations: {
    density_altitude_m: 412.7,
    air_density_ratio: 0.9617,
    energy_required_wh: 118.43,
    energy_breakdown: {
      climb_wh: 6.12,
      cruise_wh: 71.86,
      hover_wh: 37.94,
      descent_wh: 2.51,
      total_wh: 118.43,
    },
    payload_margin_kg: 0.83,
    all_up_mass_kg: 2.27,
    ground_speed_mps: 11.4,
    effective_hover_power_w: 227.6,
    battery_check: {
      energy_required_wh: 118.43,
      usable_capacity_wh: 160.13,
      margin_wh: 41.7,
      reserve_percent: 20,
      temperature_factor: 1,
      is_viable: true,
    },
    safety_flags: {
      battery_viable: true,
      payload_within_limits: true,
      wind_within_limits: true,
      gust_within_limits: true,
      temperature_within_limits: true,
      pack_temp_within_takeoff_limits: true,
      cruise_achievable: true,
    },
  },
  provenance: PROVENANCE,
  report: "",
  thread_id: "msn-7f2c41b9",
  degraded: true,
  warnings: ["Weather provider unreachable; using fallback defaults"],
};

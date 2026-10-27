// The replan comparison: what the operator reports, and how the live picture
// sits against the one that was briefed. No figure here is computed beyond a
// difference for display; every value comes from the plan or the replan.

import { SEVERITY } from "./alerts";
import type {
  AssessmentMode,
  MissionParams,
  PayloadSummary,
  PlanResult,
  RecommendedAction,
  ReplanResult,
  TelemetrySnapshotRequest,
} from "./types";

export interface TelemetryInput {
  readonly socPercent: string;
  readonly remainingLegM: string;
  readonly remainingHoverS: string;
  readonly oatC: string;
  readonly windMps: string;
  readonly payloadAttached: boolean;
}

export type SnapshotResult =
  | { readonly ok: true; readonly snapshot: TelemetrySnapshotRequest }
  | { readonly ok: false; readonly error: string };

function parse(raw: string): number | null {
  const value = Number(raw);
  return raw.trim() === "" || !Number.isFinite(value) ? null : value;
}

/**
 * The aircraft's position and altitude are the briefed ones: this form reports
 * energy, wind and what is left to fly, not a track.
 */
export function buildSnapshot(
  threadId: string,
  params: MissionParams,
  input: TelemetryInput,
  now: Date,
): SnapshotResult {
  const soc = parse(input.socPercent);
  if (soc === null || soc < 0 || soc > 100) {
    return {
      ok: false,
      error: "State of charge must be a number from 0 to 100.",
    };
  }
  const leg = parse(input.remainingLegM);
  const hover = parse(input.remainingHoverS);
  const oat = parse(input.oatC);
  if (leg === null || hover === null || oat === null) {
    return {
      ok: false,
      error:
        "Remaining leg, hover time and outside air temperature are required.",
    };
  }
  return {
    ok: true,
    snapshot: {
      thread_id: threadId,
      ts: now.toISOString(),
      latitude: params.latitude,
      longitude: params.longitude,
      alt_m: params.target_altitude_m,
      soc_fraction: soc / 100,
      remaining_leg_m: leg,
      remaining_hover_s: hover,
      oat_c: oat,
      wind_mps: parse(input.windMps),
      payload_attached: input.payloadAttached,
    },
  };
}

export interface ResidualRow {
  readonly label: string;
  readonly unit: "Wh" | "m/s" | "%";
  readonly briefed: number | null;
  readonly live: number | null;
  readonly delta: number | null;
}

function row(
  label: string,
  unit: ResidualRow["unit"],
  briefed: number | null,
  live: number | null,
): ResidualRow {
  const delta =
    briefed === null || live === null
      ? null
      : Math.round((live - briefed) * 100) / 100;
  return { label, unit, briefed, live, delta };
}

type Battery = NonNullable<PlanResult["calculations"]>["battery_check"];

/** The three energy figures the plan and the replan both computed. */
function energyRows(
  battery: Battery | null,
  live: ReplanResult["live_energy"],
): readonly ResidualRow[] {
  if (live === null) {
    return [];
  }
  return [
    row(
      "Energy available",
      "Wh",
      battery?.usable_capacity_wh ?? null,
      live.available_wh,
    ),
    row(
      "Energy required",
      "Wh",
      battery?.energy_required_wh ?? null,
      live.required_wh,
    ),
    row("Reserve", "Wh", null, live.reserve_wh),
  ];
}

/** Briefed against live, row by row, so what moved is on screen. */
export function residualRows(
  plan: PlanResult,
  sent: TelemetrySnapshotRequest,
  replan: ReplanResult,
): readonly ResidualRow[] {
  const live = replan.live_energy;
  return [
    row(
      "Margin after mission",
      "Wh",
      replan.briefed_margin_wh,
      live?.residual_wh ?? null,
    ),
    ...energyRows(plan.calculations?.battery_check ?? null, live),
    row("Wind", "m/s", plan.weather?.wind_speed_mps ?? null, sent.wind_mps),
    // The briefed plan assumes a full pack.
    row("State of charge", "%", 100, Math.round(sent.soc_fraction * 1000) / 10),
  ];
}

const ACTION_LABEL: Readonly<Record<RecommendedAction, string>> = {
  continue: "Continue",
  advisory_only: "Advisory only",
  land_soon: "Land soon",
  land_now: "Land now",
};

export interface ReplanVerdict {
  readonly mode: AssessmentMode;
  readonly action: string;
  readonly tone: "ok" | "stale" | "caution" | "critical";
}

/**
 * Operational only if the plan was sealed operational and the replan raised
 * nothing: one watch alert is enough to make it advice.
 */
export function replanVerdict(
  plan: PlanResult,
  replan: ReplanResult,
): ReplanVerdict {
  const operational =
    plan.assessment?.mode === "operational" && replan.operational_ok;
  return {
    mode: operational ? "operational" : "advisory",
    action: ACTION_LABEL[replan.recommended_action],
    tone: operational ? "ok" : SEVERITY[replan.severity].tone,
  };
}

/** Whether the brief carried a payload, the way the backend's payload check reads it. */
export function briefsPayload(
  payloads: readonly PayloadSummary[],
  payloadId: string,
): boolean {
  const briefed = payloads.find((payload) => payload.id === payloadId);
  return briefed !== undefined && briefed.weight_kg > 0;
}

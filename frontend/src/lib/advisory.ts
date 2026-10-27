// When the screen must say "not a clearance", and what it says beside it.

import type {
  AssessmentMode,
  PlanResult,
  ReplanResult,
  WeatherSource,
} from "./types";

export interface AdvisoryNotice {
  readonly mode: AssessmentMode;
  /** The briefed plan's weather source, or null if it had no reading. */
  readonly weatherSource: WeatherSource | null;
  /** How many alerts the latest replan raised, or null if none ran. */
  readonly replanAlerts: number | null;
}

function replanWithdrewClearance(replan: ReplanResult | null): boolean {
  return replan !== null && !replan.operational_ok;
}

/**
 * A plan is a clearance only if the gate sealed it operational and no replan
 * since has raised anything. Everything else is advice, including a plan with
 * no sealed assessment at all, and a clean replan never upgrades advice.
 */
export function advisoryNotice(
  plan: PlanResult | null,
  replan: ReplanResult | null,
): AdvisoryNotice | null {
  if (plan === null) {
    return null;
  }
  const sealedOperational = plan.assessment?.mode === "operational";
  if (sealedOperational && !replanWithdrewClearance(replan)) {
    return null;
  }
  return {
    mode: "advisory",
    weatherSource: plan.weather?.source ?? null,
    replanAlerts: replan === null ? null : replan.alerts.length,
  };
}

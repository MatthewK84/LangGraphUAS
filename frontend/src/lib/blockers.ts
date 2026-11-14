/** Operator-facing sentences for advisory blockers. Codes stay on the wire. */

export const BLOCKER_REASONS: Readonly<Record<string, string>> = {
  WEATHER_NOT_LIVE: "Weather is not a live or fresh cached observation.",
  WEATHER_DEGRADED: "The weather reading is degraded.",
  ASSESSMENT_INCOMPLETE: "The mission could not be fully assessed.",
  PROVENANCE_INCOMPLETE: "A required figure has no provenance record.",
  POWER_NOT_OPERATIONAL_GRADE:
    "An energy-budget figure is not from a datasheet or flight log.",
  FIELD_NOT_OPERATIONAL_GRADE:
    "A required figure is not from a datasheet or flight log.",
  CONFIGURATION_NOT_LAB_OPERATIONAL:
    "Operational mode is only considered for the lab configuration Freefly Astro Max + Sony ILX-LR1.",
  BLUE_LIST_SNAPSHOT_UNAVAILABLE:
    "No usable Blue UAS snapshot is stored, so configuration clearance cannot be asserted.",
  BLUE_LIST_SNAPSHOT_STALE:
    "The pinned Blue UAS snapshot is older than the configured maximum age, so an operational claim would describe the past. Verify the current list at bluelist.dcma.mil before flight.",
  CORPUS_QUARANTINED:
    "Corpus chunks for this configuration are awaiting review.",
};

export function blockerReason(code: string): string | undefined {
  return BLOCKER_REASONS[code];
}

import type { FigureProvenance } from "@/lib/types";

export interface FigureTag {
  readonly label: string;
  readonly operationalGrade: boolean;
}

/**
 * How one W or Wh figure is labelled on screen (#79). A figure the backend did
 * not label is unverified: absence of provenance is never read as a measurement.
 */
export function figureTag(
  provenance: FigureProvenance,
  path: string,
): FigureTag {
  const entry = provenance[path];
  if (entry === undefined) {
    return { label: "unverified", operationalGrade: false };
  }
  if (entry.operational_grade) {
    return { label: entry.source, operationalGrade: true };
  }
  return {
    label: `${entry.source}, ${entry.confidence} confidence`,
    operationalGrade: false,
  };
}

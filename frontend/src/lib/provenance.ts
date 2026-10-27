import type {
  Confidence,
  FieldSource,
  FigureProvenance,
  InputBasis,
  NumberProvenance,
} from "@/lib/types";

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

const SOURCE_LABEL: Readonly<Record<FieldSource, string>> = {
  datasheet: "Datasheet",
  flight_log: "Flight log",
  secondary: "Secondary source",
  derived: "Derived",
  estimate: "Estimate",
  unknown: "Not recorded",
};

// The backend gate's own list (schemas/provenance.py OPERATIONAL_GRADE).
const OPERATIONAL_SOURCES: ReadonlySet<FieldSource> = new Set([
  "datasheet",
  "flight_log",
]);

export interface BasisEntry {
  readonly field: string;
  readonly value: number | null;
  readonly unit: string;
  readonly sourceLabel: string;
  readonly operationalGrade: boolean;
  readonly confidence: Confidence;
  readonly citation: { readonly href: string; readonly text: string } | null;
  readonly retrieved: string | null;
  readonly notes: string;
}

/** Only web links are followed; anything else stays plain text. */
function citation(url: string | null): BasisEntry["citation"] {
  if (url === null || !/^https?:\/\//.test(url)) {
    return null;
  }
  return { href: url, text: url.replace(/^https?:\/\//, "") };
}

/** A date stays as recorded; a timestamp is shown in UTC. */
function retrieved(stamp: string | null): string | null {
  if (stamp === null || /^\d{4}-\d{2}-\d{2}$/.test(stamp)) {
    return stamp;
  }
  const time = new Date(stamp);
  if (Number.isNaN(time.getTime())) {
    return stamp;
  }
  return `${time.toISOString().slice(0, 16).replace("T", " ")}Z`;
}

/** The drawer's rows (#96): each input field, its source and its citation. */
export function basisEntries(entry: NumberProvenance): readonly BasisEntry[] {
  return entry.basis.map((input: InputBasis) => ({
    field: input.field,
    value: input.value,
    unit: input.unit ?? "",
    sourceLabel: SOURCE_LABEL[input.source],
    operationalGrade: OPERATIONAL_SOURCES.has(input.source),
    confidence: input.confidence,
    citation: citation(input.source_url),
    retrieved: retrieved(input.retrieved_at),
    notes: input.notes,
  }));
}

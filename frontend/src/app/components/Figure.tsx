import type { JSX } from "react";

import { figureTag } from "@/lib/provenance";
import type { FigureProvenance } from "@/lib/types";

/**
 * What a W or Wh figure rests on, for the Basis column (#79). Anything short
 * of operational grade renders in the caution color with its confidence, so a
 * guessed watt never reads as measured.
 */
export function Figure({
  path,
  provenance,
}: {
  readonly path: string;
  readonly provenance: FigureProvenance;
}): JSX.Element {
  const tag = figureTag(provenance, path);
  return (
    <span
      className={tag.operationalGrade ? "text-fg-secondary" : "text-caution"}
      title={provenance[path]?.inputs.join(", ") ?? "no provenance reported"}
    >
      {tag.label}
    </span>
  );
}

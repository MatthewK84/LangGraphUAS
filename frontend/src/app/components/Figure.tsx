import type { JSX } from "react";

import { figureTag } from "@/lib/provenance";
import type { FigureProvenance } from "@/lib/types";

/**
 * A W or Wh figure with what it rests on beside it (#79). Anything short of
 * operational grade renders amber, so a guessed watt never reads as measured.
 */
export function Figure({
  value,
  unit,
  path,
  provenance,
}: {
  readonly value: number;
  readonly unit: "W" | "Wh";
  readonly path: string;
  readonly provenance: FigureProvenance;
}): JSX.Element {
  const tag = figureTag(provenance, path);
  return (
    <>
      {value} {unit}
      <span
        className={`ml-2 text-xs font-normal ${tag.operationalGrade ? "text-slate-400" : "text-amber-400"}`}
        title={provenance[path]?.inputs.join(", ") ?? "no provenance reported"}
      >
        ({tag.label})
      </span>
    </>
  );
}

import { useContext } from "react";
import type { JSX } from "react";

import { InspectContext } from "@/lib/inspect";
import type { InspectedFigure } from "@/lib/inspect";
import { figureTag } from "@/lib/provenance";
import type { FigureProvenance } from "@/lib/types";

/**
 * What a W or Wh figure rests on, for the Basis column (#79). Anything short
 * of operational grade renders in the caution color with its confidence, so a
 * guessed watt never reads as measured. Where the page offers it, the label
 * opens the figure's provenance drawer (#96).
 */
export function Figure({
  figure,
  provenance,
}: {
  readonly figure: InspectedFigure;
  readonly provenance: FigureProvenance;
}): JSX.Element {
  const inspect = useContext(InspectContext);
  const tag = figureTag(provenance, figure.path);
  const tone = tag.operationalGrade ? "text-fg-secondary" : "text-caution";
  if (inspect === null) {
    return <span className={tone}>{tag.label}</span>;
  }
  return (
    <button
      type="button"
      className={`max-w-full truncate text-left underline decoration-line-strong underline-offset-2 hover:decoration-current ${tone}`}
      aria-label={`${tag.label}: show the provenance of ${figure.label}`}
      onClick={(event) => {
        inspect(figure, event.currentTarget);
      }}
    >
      {tag.label}
    </button>
  );
}

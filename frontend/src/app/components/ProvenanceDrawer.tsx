"use client";

import { useEffect, useRef } from "react";
import type { JSX } from "react";

import type { InspectedFigure } from "@/lib/inspect";
import type { BasisEntry } from "@/lib/provenance";
import { basisEntries, figureTag } from "@/lib/provenance";
import type { FigureProvenance } from "@/lib/types";

function Cited({ entry }: { readonly entry: BasisEntry }): JSX.Element {
  if (entry.citation === null) {
    return <span className="text-fg-muted">no citation</span>;
  }
  return (
    <a
      href={entry.citation.href}
      target="_blank"
      rel="noopener noreferrer"
      className="text-accent underline underline-offset-2"
      title={entry.citation.href}
    >
      {entry.citation.text}
    </a>
  );
}

function BasisRow({ entry }: { readonly entry: BasisEntry }): JSX.Element {
  const tone = entry.operationalGrade ? "text-fg-secondary" : "text-caution";
  return (
    <tbody className="border-b border-line-subtle hover:bg-hover">
      <tr className="h-row-dense whitespace-nowrap align-bottom">
        <th
          scope="row"
          className="truncate px-3 text-left font-mono text-sm font-normal text-fg"
        >
          {entry.field}
        </th>
        <td className="px-2 text-right font-medium text-fg">
          {entry.value ?? "none"}
        </td>
        <td className="px-2 text-left text-fg-muted">{entry.unit}</td>
        <td className={`truncate px-2 text-left ${tone}`}>
          {entry.sourceLabel}
        </td>
        <td className="px-2 text-left text-fg-secondary">{entry.confidence}</td>
        <td className="px-3 text-left font-mono text-sm text-fg-secondary">
          {entry.retrieved ?? "not recorded"}
        </td>
      </tr>
      <tr className="h-row-dense align-top text-sm">
        <td colSpan={6} className="truncate px-3 pb-1 text-fg-secondary">
          <Cited entry={entry} />
          {entry.notes !== "" && (
            <span title={entry.notes}>
              <span className="px-2 text-fg-muted">&middot;</span>
              {entry.notes}
            </span>
          )}
        </td>
      </tr>
    </tbody>
  );
}

const COLUMNS = [
  { heading: "Field", width: "w-1/3" },
  { heading: "Value", width: "w-1/12" },
  { heading: "Unit", width: "w-1/12" },
  { heading: "Source", width: "w-1/6" },
  { heading: "Confidence", width: "w-1/6" },
  { heading: "Retrieved", width: "" },
];

/**
 * Where one W or Wh figure came from (#96): each catalog field it rests on,
 * that field's source, confidence and retrieval date, and a link to the
 * document it cites. Non-modal and docked under the figures, so the review
 * controls stay reachable; Escape closes it.
 */
export function ProvenanceDrawer({
  figure,
  provenance,
  onClose,
}: {
  readonly figure: InspectedFigure;
  readonly provenance: FigureProvenance;
  readonly onClose: () => void;
}): JSX.Element {
  const close = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    close.current?.focus();
    const onKey = (event: KeyboardEvent): void => {
      if (event.key === "Escape") {
        onClose();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
    };
  }, [figure, onClose]);
  const entry = provenance[figure.path];
  const tag = figureTag(provenance, figure.path);
  return (
    <section
      aria-label={`Provenance: ${figure.label}`}
      className="flex h-drawer shrink-0 flex-col border-t border-line-strong bg-panel"
    >
      <div className="panel-header">
        <h3 className="section-label">
          Provenance &middot; {figure.label}
          <span className="ml-2 font-mono normal-case tracking-normal text-fg">
            {figure.value ?? ""} {figure.unit}
          </span>
        </h3>
        <button ref={close} type="button" className="btn" onClick={onClose}>
          Close
        </button>
      </div>
      <p className="border-b border-line px-3 py-2 text-sm text-fg-secondary">
        Basis{" "}
        <span className={tag.operationalGrade ? "text-fg" : "text-caution"}>
          {tag.label}
        </span>
        : the weakest of the fields below.{" "}
        {tag.operationalGrade
          ? "Every field is operational grade."
          : "At least one field is not operational grade."}
      </p>
      <div className="min-h-0 flex-1 overflow-y-auto">
        <table className="w-full table-fixed border-collapse text-md">
          <colgroup>
            {COLUMNS.map((column) => (
              <col key={column.heading} className={column.width} />
            ))}
          </colgroup>
          <thead>
            <tr className="h-row border-b border-line text-sm text-fg-muted">
              {COLUMNS.map((column) => (
                <th
                  key={column.heading}
                  scope="col"
                  className={`px-2 font-normal first:px-3 ${column.heading === "Value" ? "text-right" : "text-left"}`}
                >
                  {column.heading}
                </th>
              ))}
            </tr>
          </thead>
          {(entry === undefined ? [] : basisEntries(entry)).map((row) => (
            <BasisRow key={row.field} entry={row} />
          ))}
        </table>
        {(entry === undefined || entry.basis.length === 0) && (
          <p className="px-3 py-2 text-sm text-fg-muted">
            The backend reported no field records for this figure.
          </p>
        )}
      </div>
    </section>
  );
}

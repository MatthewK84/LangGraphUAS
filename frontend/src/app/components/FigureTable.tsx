import type { JSX, ReactNode } from "react";

import type { FigureProvenance } from "@/lib/types";

import { Figure } from "./Figure";

interface RowBase {
  readonly label: string;
  readonly value: ReactNode;
  readonly tone?: "ok" | "critical";
  readonly note?: string;
}

/**
 * One readout row. A W or Wh figure cannot be written without the dotted
 * path of its provenance entry (#79), so no watt renders without its basis.
 */
export type FigureRow =
  | (RowBase & {
      readonly unit: "" | "°C" | "m/s" | "m MSL" | "%" | "kg";
      readonly path?: undefined;
    })
  | (RowBase & { readonly unit: "W" | "Wh"; readonly path: string });

const TONE: Readonly<Record<"ok" | "critical", string>> = {
  ok: "text-ok",
  critical: "text-critical",
};

/** The Basis cell: a figure's provenance, or the row's note. */
function Basis({
  row,
  provenance,
}: {
  readonly row: FigureRow;
  readonly provenance: FigureProvenance;
}): JSX.Element {
  if (row.path === undefined) {
    return <span className="text-fg-muted">{row.note ?? ""}</span>;
  }
  return (
    <Figure
      figure={{
        path: row.path,
        label: row.label,
        value: typeof row.value === "number" ? row.value : null,
        unit: row.unit,
      }}
      provenance={provenance}
    />
  );
}

function Row({
  row,
  provenance,
}: {
  readonly row: FigureRow;
  readonly provenance: FigureProvenance;
}): JSX.Element {
  const tone = row.tone === undefined ? "text-fg" : TONE[row.tone];
  // Numbers right-align on their digits; words read from the left.
  const align = typeof row.value === "number" ? "text-right" : "text-left";
  // A worded reading with no unit or basis takes the row's full width.
  const wordOnly = align === "text-left" && row.unit === "";
  return (
    <tr className="h-row whitespace-nowrap border-b border-line-subtle hover:bg-hover">
      <th
        scope="row"
        className="truncate px-3 text-left font-normal text-fg-secondary"
        title={row.note ?? row.label}
      >
        {row.label}
      </th>
      <td
        className={`truncate px-2 font-medium ${align} ${tone}`}
        title={typeof row.value === "string" ? row.value : undefined}
        colSpan={wordOnly ? 3 : 1}
      >
        {row.value}
      </td>
      {!wordOnly && (
        <>
          <td className="px-2 text-left text-fg-muted">{row.unit}</td>
          <td className="truncate px-3 text-left text-sm">
            <Basis row={row} provenance={provenance} />
          </td>
        </>
      )}
    </tr>
  );
}

/** A dense, titled readout table: label, value, unit, basis. */
export function FigureTable({
  title,
  rows,
  provenance,
}: {
  readonly title: string;
  readonly rows: readonly FigureRow[];
  readonly provenance: FigureProvenance;
}): JSX.Element {
  return (
    <table className="w-full table-fixed border-collapse text-md">
      <caption className="section-label h-header bg-raised px-3 text-left align-middle leading-none">
        <span className="flex h-header items-center">{title}</span>
      </caption>
      <colgroup>
        <col className="w-1/3" />
        <col className="w-1/6" />
        <col className="w-1/12" />
        <col />
      </colgroup>
      <thead className="sr-only">
        <tr>
          <th scope="col">Figure</th>
          <th scope="col">Value</th>
          <th scope="col">Unit</th>
          <th scope="col">Basis</th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <Row key={row.label} row={row} provenance={provenance} />
        ))}
      </tbody>
    </table>
  );
}

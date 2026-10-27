// Opening a figure's provenance (#96) from any table without threading a
// callback through every panel. No provider means no drawer: the basis cell
// stays plain text.

import { createContext } from "react";

export interface InspectedFigure {
  readonly path: string;
  readonly label: string;
  readonly value: number | null;
  readonly unit: string;
}

export type InspectFigure = (
  figure: InspectedFigure,
  trigger: HTMLElement,
) => void;

export const InspectContext = createContext<InspectFigure | null>(null);

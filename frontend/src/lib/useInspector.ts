"use client";

// Which figure's provenance is open (#96), and the control that opened it, so
// closing the drawer puts keyboard focus back where the operator was.

import { useCallback, useRef, useState } from "react";

import type { InspectedFigure, InspectFigure } from "./inspect";

export interface Inspector {
  readonly figure: InspectedFigure | null;
  readonly open: InspectFigure;
  readonly close: () => void;
  readonly reset: () => void;
}

export function useInspector(): Inspector {
  const [figure, setFigure] = useState<InspectedFigure | null>(null);
  const trigger = useRef<HTMLElement | null>(null);
  const open = useCallback<InspectFigure>((next, from) => {
    trigger.current = from;
    setFigure(next);
  }, []);
  const close = useCallback(() => {
    setFigure(null);
    trigger.current?.focus();
  }, []);
  const reset = useCallback(() => {
    setFigure(null);
  }, []);
  return { figure, open, close, reset };
}

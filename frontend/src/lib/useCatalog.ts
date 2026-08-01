"use client";

// Loads the selectable aircraft and payload catalog from the backend so the UI
// never duplicates the reference data that the API already owns.

import { useEffect, useState } from "react";

import { fetchAircraft, fetchPayloads } from "@/lib/api";
import type { AircraftSummary, PayloadSummary } from "@/lib/types";

export interface CatalogState {
  readonly aircraft: readonly AircraftSummary[];
  readonly payloads: readonly PayloadSummary[];
  readonly loading: boolean;
  readonly error: string | null;
}

const EMPTY: CatalogState = {
  aircraft: [],
  payloads: [],
  loading: true,
  error: null,
};

export function useCatalog(): CatalogState {
  const [state, setState] = useState<CatalogState>(EMPTY);

  useEffect(() => {
    let cancelled = false;

    async function load(): Promise<void> {
      const [aircraftResult, payloadResult] = await Promise.all([
        fetchAircraft(),
        fetchPayloads(),
      ]);
      if (cancelled) {
        return;
      }
      if (!aircraftResult.ok) {
        setState({
          aircraft: [],
          payloads: [],
          loading: false,
          error: aircraftResult.error,
        });
        return;
      }
      if (!payloadResult.ok) {
        setState({
          aircraft: [],
          payloads: [],
          loading: false,
          error: payloadResult.error,
        });
        return;
      }
      setState({
        aircraft: aircraftResult.data,
        payloads: payloadResult.data,
        loading: false,
        error: null,
      });
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  return state;
}

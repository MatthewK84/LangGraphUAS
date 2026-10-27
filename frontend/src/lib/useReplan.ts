"use client";

// The page's replan state: the snapshot last sent, what came back, and why a
// request could not be made. Cleared whenever a new plan is computed.

import { useState } from "react";

import { requestReplan } from "./api";
import type { TelemetryInput } from "./replan";
import { buildSnapshot } from "./replan";
import type {
  MissionParams,
  ReplanResult,
  TelemetrySnapshotRequest,
} from "./types";

export interface ReplanRecord {
  readonly sent: TelemetrySnapshotRequest;
  readonly result: ReplanResult;
}

export interface ReplanState {
  readonly latest: ReplanRecord | null;
  readonly error: string | null;
  readonly busy: boolean;
  readonly run: (
    threadId: string,
    params: MissionParams,
    input: TelemetryInput,
  ) => Promise<void>;
  readonly reset: () => void;
}

export function useReplan(): ReplanState {
  const [latest, setLatest] = useState<ReplanRecord | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run(
    threadId: string,
    params: MissionParams,
    input: TelemetryInput,
  ): Promise<void> {
    const built = buildSnapshot(threadId, params, input, new Date());
    if (!built.ok) {
      setError(built.error);
      return;
    }
    setBusy(true);
    setError(null);
    const outcome = await requestReplan(built.snapshot);
    setBusy(false);
    if (!outcome.ok) {
      setError(`Unable to replan: ${outcome.error}`);
      return;
    }
    setLatest({ sent: built.snapshot, result: outcome.data });
  }

  function reset(): void {
    setLatest(null);
    setError(null);
  }

  return { latest, error, busy, run, reset };
}

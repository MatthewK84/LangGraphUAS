"use client";

import { useState } from "react";
import type { JSX } from "react";

import type { TelemetryInput } from "@/lib/replan";

import { NumberField } from "./NumberField";

interface ReplanFormProps {
  readonly busy: boolean;
  /** The payload state the brief assumed; the form starts from it. */
  readonly payloadBriefed: boolean;
  readonly error: string | null;
  readonly onReplan: (input: TelemetryInput) => void;
}

/** Live telemetry for a signed plan: what is left in the pack and to fly. */
export function ReplanForm({
  busy,
  payloadBriefed,
  error,
  onReplan,
}: ReplanFormProps): JSX.Element {
  const [socPercent, setSoc] = useState("");
  const [remainingLegM, setLeg] = useState("");
  const [remainingHoverS, setHover] = useState("0");
  const [oatC, setOat] = useState("");
  const [windMps, setWind] = useState("");
  const [payloadAttached, setPayload] = useState(payloadBriefed);
  return (
    <form
      aria-label="Live telemetry"
      className="space-y-3 border-t border-line p-3"
      onSubmit={(event) => {
        event.preventDefault();
        onReplan({
          socPercent,
          remainingLegM,
          remainingHoverS,
          oatC,
          windMps,
          payloadAttached,
        });
      }}
    >
      <h3 className="section-label">Replan against live telemetry</h3>
      <div className="grid grid-cols-2 gap-2">
        <NumberField
          id="soc"
          label="State of charge (%)"
          value={socPercent}
          onChange={setSoc}
        />
        <NumberField
          id="oat"
          label="Outside air (°C)"
          value={oatC}
          onChange={setOat}
        />
        <NumberField
          id="leg"
          label="Remaining leg (m)"
          value={remainingLegM}
          onChange={setLeg}
        />
        <NumberField
          id="remaining-hover"
          label="Remaining hover (s)"
          value={remainingHoverS}
          onChange={setHover}
        />
        <NumberField
          id="wind"
          label="Wind (m/s)"
          value={windMps}
          placeholder="not reported"
          optional
          onChange={setWind}
        />
      </div>
      <label className="flex items-center gap-2 text-md text-fg">
        <input
          type="checkbox"
          className="accent-accent"
          checked={payloadAttached}
          onChange={(event) => {
            setPayload(event.target.checked);
          }}
        />
        Payload attached
      </label>
      {error !== null && (
        <p role="alert" className="text-sm text-critical">
          {error}
        </p>
      )}
      <button type="submit" disabled={busy} className="btn w-full">
        {busy ? "Working..." : "Replan against telemetry"}
      </button>
    </form>
  );
}

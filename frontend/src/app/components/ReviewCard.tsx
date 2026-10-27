"use client";

import { useState } from "react";
import type { JSX } from "react";

import type { Assessment } from "@/lib/types";

interface ReviewCardProps {
  readonly assessment: Assessment;
  readonly busy: boolean;
  readonly onConfirm: () => void;
  readonly onAbort: () => void;
}

function verdictLabel(assessment: Assessment): string {
  if (assessment.decision === "insufficient_data") {
    return "NOT ASSESSED";
  }
  return assessment.decision === "go" ? "GO" : "NO-GO";
}

/**
 * The review step. Nothing downstream runs until an operator acts here: the
 * brief is generated after this signature, not before it, so what is shown has
 * been touched by the calculator alone.
 */
export function ReviewCard({
  assessment,
  busy,
  onConfirm,
  onAbort,
}: ReviewCardProps): JSX.Element {
  const [understood, setUnderstood] = useState(false);
  const advisory = assessment.mode === "advisory";
  const canConfirm = !busy && (!advisory || understood);

  return (
    <section className="space-y-3 p-3" aria-label="Assessment review">
      <div className="border-l-2 border-caution bg-caution-tint px-3 py-2">
        <span className="section-label text-caution">
          Awaiting acknowledgement
        </span>
        <p className="mt-1 text-xl font-semibold text-fg">
          {verdictLabel(assessment)} &middot; {assessment.mode}
        </p>
        <p className="mt-1 font-mono text-xs text-fg-secondary">
          calculator {assessment.calculator_version} &middot; inputs{" "}
          {assessment.inputs_hash.slice(0, 12)}
        </p>
      </div>

      {assessment.reasons.length > 0 && (
        <div>
          <span className="section-label">Limiting factors</span>
          <ul className="mt-1 list-inside list-disc space-y-1 text-md text-fg-secondary">
            {assessment.reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </div>
      )}

      {advisory && (
        <label className="flex items-start gap-2 text-md text-fg">
          <input
            type="checkbox"
            className="mt-1 accent-accent"
            checked={understood}
            onChange={(event) => {
              setUnderstood(event.target.checked);
            }}
          />
          <span>
            I understand this plan is advisory and is not cleared for
            operational use.
          </span>
        </label>
      )}

      <div className="flex gap-2">
        <button
          type="button"
          disabled={!canConfirm}
          onClick={onConfirm}
          className="btn btn-primary flex-1"
        >
          {busy ? "Working..." : "Acknowledge and generate brief"}
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={onAbort}
          className="btn text-critical"
        >
          Abort
        </button>
      </div>
    </section>
  );
}

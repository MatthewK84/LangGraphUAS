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
    <section
      className="p-4 rounded-xl border bg-slate-800 border-amber-700 space-y-4"
      aria-label="Assessment review"
    >
      <div>
        <span className="text-xs font-semibold text-amber-300 uppercase tracking-wider">
          Awaiting acknowledgement
        </span>
        <p className="mt-1 text-lg font-bold text-slate-100">
          {verdictLabel(assessment)} &middot; {assessment.mode}
        </p>
        <p className="text-xs text-slate-400 font-mono mt-1">
          calculator {assessment.calculator_version} &middot; inputs{" "}
          {assessment.inputs_hash.slice(0, 12)}
        </p>
      </div>

      {assessment.reasons.length > 0 && (
        <div>
          <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
            Limiting factors
          </span>
          <ul className="mt-1 space-y-1 text-sm list-disc list-inside text-slate-300">
            {assessment.reasons.map((reason) => (
              <li key={reason}>{reason}</li>
            ))}
          </ul>
        </div>
      )}

      {advisory && (
        <label className="flex items-start gap-2 text-sm text-amber-200">
          <input
            type="checkbox"
            className="mt-1"
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

      <div className="flex gap-3">
        <button
          type="button"
          disabled={!canConfirm}
          onClick={onConfirm}
          className="px-4 py-2 rounded-lg bg-emerald-700 text-white text-sm font-semibold disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {busy ? "Working..." : "Acknowledge and generate brief"}
        </button>
        <button
          type="button"
          disabled={busy}
          onClick={onAbort}
          className="px-4 py-2 rounded-lg border border-rose-700 text-rose-300 text-sm font-semibold disabled:opacity-40"
        >
          Abort
        </button>
      </div>
    </section>
  );
}

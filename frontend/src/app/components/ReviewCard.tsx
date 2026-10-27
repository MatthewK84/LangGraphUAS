"use client";

import { useState } from "react";
import type { JSX } from "react";

import { confirmBlocker } from "@/lib/review";
import type { Assessment } from "@/lib/types";

interface ReviewCardProps {
  readonly assessment: Assessment;
  readonly busy: boolean;
  /** A mission input changed after this assessment was computed. */
  readonly inputsEdited: boolean;
  readonly onConfirm: () => void;
  readonly onAbort: () => void;
}

function verdictLabel(assessment: Assessment): string {
  if (assessment.decision === "insufficient_data") {
    return "NOT ASSESSED";
  }
  return assessment.decision === "go" ? "GO" : "NO-GO";
}

function SealedSummary({
  assessment,
  hash,
}: {
  readonly assessment: Assessment;
  readonly hash: string;
}): JSX.Element {
  return (
    <div className="border-l-2 border-caution bg-caution-tint px-3 py-2">
      <span className="section-label text-caution">
        Awaiting acknowledgement
      </span>
      <p className="mt-1 text-xl font-semibold text-fg">
        {verdictLabel(assessment)} &middot; {assessment.mode}
      </p>
      <dl className="mt-1 grid grid-cols-[auto_1fr] gap-x-2 text-xs">
        <dt className="text-fg-muted">Calculator</dt>
        <dd className="font-mono text-fg-secondary">
          {assessment.calculator_version}
        </dd>
        <dt className="text-fg-muted">Inputs hash</dt>
        <dd className="break-all font-mono text-fg-secondary">{hash}</dd>
      </dl>
    </div>
  );
}

/**
 * The review step. Nothing downstream runs until an operator acts here: the
 * brief is generated after this signature, not before it, so what is shown has
 * been touched by the calculator alone. Confirm signs the hash displayed here,
 * and only while it is still the assessment's and no input has moved since.
 */
export function ReviewCard({
  assessment,
  busy,
  inputsEdited,
  onConfirm,
  onAbort,
}: ReviewCardProps): JSX.Element {
  const [understood, setUnderstood] = useState(false);
  const [reviewedHash, setReviewedHash] = useState(assessment.inputs_hash);
  const advisory = assessment.mode === "advisory";
  const changed = reviewedHash !== assessment.inputs_hash;
  // Signing what is on screen is no longer signing what was computed.
  const stale = changed || inputsEdited;
  const blocker = confirmBlocker({
    busy,
    advisory,
    understood,
    reviewedHash,
    currentHash: assessment.inputs_hash,
    inputsEdited,
  });

  return (
    <section className="space-y-3 p-3" aria-label="Assessment review">
      <SealedSummary assessment={assessment} hash={reviewedHash} />

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
          disabled={blocker !== null}
          aria-describedby={blocker === null ? undefined : "confirm-blocker"}
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
      {blocker !== null && (
        <p
          id="confirm-blocker"
          className={`text-sm ${stale ? "text-caution" : "text-fg-muted"}`}
        >
          {blocker}
        </p>
      )}
      {changed && (
        <button
          type="button"
          className="btn w-full"
          onClick={() => {
            setReviewedHash(assessment.inputs_hash);
            setUnderstood(false);
          }}
        >
          Review the new assessment
        </button>
      )}
    </section>
  );
}

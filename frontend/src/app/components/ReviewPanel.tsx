import { useEffect, useRef } from "react";
import type { JSX } from "react";

import type { TelemetryInput } from "@/lib/replan";
import type { AckAction, PlanResult } from "@/lib/types";

import { ReplanForm } from "./ReplanForm";
import { ReviewCard } from "./ReviewCard";

interface ReviewPanelProps {
  readonly result: PlanResult | null;
  readonly busy: boolean;
  /** A mission input changed after the pending assessment was computed. */
  readonly inputsEdited: boolean;
  readonly onDecide: (action: AckAction) => void;
  readonly replanBusy: boolean;
  readonly payloadBriefed: boolean;
  readonly replanError: string | null;
  readonly onReplan: (input: TelemetryInput) => void;
}

/** A replan compares against a signed brief, so it is offered only after one. */
function canReplan(result: PlanResult | null): boolean {
  return result?.assessment != null && !result.awaiting_ack && !result.aborted;
}

function idleText(result: PlanResult | null): string {
  if (result?.aborted === true) {
    return "Assessment aborted. No brief was written.";
  }
  if (result?.assessment != null) {
    return "Assessment signed. The brief is in the assessment panel.";
  }
  return "No assessment awaiting a signature. Analyze a mission to compute one.";
}

/**
 * What became of the assessment just signed or aborted. The card that held
 * keyboard focus is gone, so focus moves here rather than falling to the body.
 */
function Decided({ text }: { readonly text: string }): JSX.Element {
  const note = useRef<HTMLParagraphElement>(null);
  useEffect(() => {
    note.current?.focus();
  }, []);
  return (
    <p ref={note} tabIndex={-1} className="p-3 text-sm text-fg-muted">
      {text}
    </p>
  );
}

function Outcome({
  result,
}: {
  readonly result: PlanResult | null;
}): JSX.Element {
  if (result?.assessment != null) {
    return <Decided text={idleText(result)} />;
  }
  return <p className="p-3 text-sm text-fg-muted">{idleText(result)}</p>;
}

/** The inspector column: where a sealed assessment is signed or aborted. */
export function ReviewPanel(props: ReviewPanelProps): JSX.Element {
  const { result, busy, inputsEdited, onDecide } = props;
  const { replanBusy, replanError, onReplan, payloadBriefed } = props;
  const pending =
    result !== null && result.awaiting_ack && result.assessment !== null
      ? result.assessment
      : null;
  return (
    <aside
      className="flex w-inspector shrink-0 flex-col bg-panel"
      aria-label="Review and acknowledge"
    >
      <div className="panel-header">
        <h2 className="section-label">Review and acknowledge</h2>
      </div>
      <div className="relative min-h-0 flex-1 overflow-y-auto">
        {pending === null && <Outcome result={result} />}
        {pending !== null && (
          <ReviewCard
            assessment={pending}
            busy={busy}
            inputsEdited={inputsEdited}
            onConfirm={() => {
              onDecide("confirm");
            }}
            onAbort={() => {
              onDecide("abort");
            }}
          />
        )}
        {canReplan(result) && (
          <ReplanForm
            busy={replanBusy}
            payloadBriefed={payloadBriefed}
            error={replanError}
            onReplan={onReplan}
          />
        )}
      </div>
    </aside>
  );
}

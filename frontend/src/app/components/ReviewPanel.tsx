import type { JSX } from "react";

import type { AckAction, PlanResult } from "@/lib/types";

import { ReviewCard } from "./ReviewCard";

interface ReviewPanelProps {
  readonly result: PlanResult | null;
  readonly busy: boolean;
  readonly onDecide: (action: AckAction) => void;
}

/** The inspector column: where a sealed assessment is signed or aborted. */
export function ReviewPanel(props: ReviewPanelProps): JSX.Element {
  const { result, busy, onDecide } = props;
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
      <div className="min-h-0 flex-1 overflow-y-auto">
        {pending === null ? (
          <p className="p-3 text-sm text-fg-muted">
            No assessment awaiting a signature. Analyze a mission to compute
            one.
          </p>
        ) : (
          <ReviewCard
            assessment={pending}
            busy={busy}
            onConfirm={() => {
              onDecide("confirm");
            }}
            onAbort={() => {
              onDecide("abort");
            }}
          />
        )}
      </div>
    </aside>
  );
}

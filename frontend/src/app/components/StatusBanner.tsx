import type { JSX } from "react";

import type { PlanResult } from "@/lib/types";

type Tone = "ok" | "caution" | "critical";

const TONE_CLASS: Readonly<Record<Tone, string>> = {
  ok: "border-ok bg-ok-tint",
  caution: "border-caution bg-caution-tint",
  critical: "border-critical bg-critical-tint",
};

const TONE_TEXT: Readonly<Record<Tone, string>> = {
  ok: "text-ok",
  caution: "text-caution",
  critical: "text-critical",
};

/**
 * Green is reserved for an operational GO. An advisory plan is planning
 * support, so it renders amber however good the numbers look: the one thing
 * this banner must never do is read as clearance it did not grant.
 */
function bannerTone(result: PlanResult): Tone {
  if (!result.is_viable) {
    return "critical";
  }
  if (result.assessment?.mode === "operational") {
    return "ok";
  }
  return "caution";
}

function bannerLabel(result: PlanResult): string {
  if (result.assessment?.decision === "insufficient_data") {
    return "INSUFFICIENT DATA (NOT ASSESSED)";
  }
  if (!result.is_viable) {
    return "MISSION DENIED (NO-GO)";
  }
  if (result.assessment?.mode === "operational") {
    return "CLEAR TO LAUNCH (GO)";
  }
  return "ADVISORY GO - NOT FOR OPERATIONAL USE";
}

export function StatusBanner({
  result,
}: {
  readonly result: PlanResult;
}): JSX.Element {
  const tone = bannerTone(result);
  return (
    <div
      className={`flex h-strip items-center justify-between border-b border-l-4 border-b-line px-3 ${TONE_CLASS[tone]}`}
    >
      <div>
        <p className="text-sm text-fg-secondary">Flight dispatch status</p>
        <p className={`text-xl font-semibold ${TONE_TEXT[tone]}`}>
          {bannerLabel(result)}
        </p>
      </div>
      <p className="text-sm text-fg-secondary">
        Thread <span className="font-mono text-fg">{result.thread_id}</span>
      </p>
    </div>
  );
}

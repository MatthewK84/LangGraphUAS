import type { JSX } from "react";

import { ALERT_CODES, SEVERITY } from "@/lib/alerts";
import type { ResidualRow } from "@/lib/replan";
import { replanVerdict, residualRows } from "@/lib/replan";
import type {
  PlanResult,
  ReplanAlert,
  ReplanResult,
  TelemetrySnapshotRequest,
} from "@/lib/types";

const TONE_CLASS = {
  ok: "border-ok bg-ok-tint text-ok",
  stale: "border-stale bg-stale-tint text-stale",
  caution: "border-caution bg-caution-tint text-caution",
  critical: "border-critical bg-critical-tint text-critical",
} as const;

const TONE_TEXT = {
  stale: "text-stale",
  caution: "text-caution",
  critical: "text-critical",
} as const;

function signed(delta: number | null): string {
  if (delta === null) {
    return "";
  }
  return delta > 0 ? `+${String(delta)}` : String(delta);
}

function Comparison({
  rows,
}: {
  readonly rows: readonly ResidualRow[];
}): JSX.Element {
  return (
    <table className="w-full table-fixed border-collapse text-md">
      <caption className="section-label h-header bg-raised px-3 text-left align-middle leading-none">
        <span className="flex h-header items-center">Briefed against live</span>
      </caption>
      <colgroup>
        <col className="w-1/3" />
        <col />
        <col />
        <col />
        <col className="w-1/12" />
      </colgroup>
      <thead>
        <tr className="h-row border-b border-line text-sm text-fg-muted">
          <th scope="col" className="px-3 text-left font-normal">
            Figure
          </th>
          <th scope="col" className="px-2 text-right font-normal">
            Briefed
          </th>
          <th scope="col" className="px-2 text-right font-normal">
            Live
          </th>
          <th scope="col" className="px-2 text-right font-normal">
            Change
          </th>
          <th scope="col" className="px-2 text-left font-normal">
            Unit
          </th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr
            key={row.label}
            className="h-row whitespace-nowrap border-b border-line-subtle hover:bg-hover"
          >
            <th
              scope="row"
              className="truncate px-3 text-left font-normal text-fg-secondary"
            >
              {row.label}
            </th>
            <td className="px-2 text-right text-fg-secondary">
              {row.briefed ?? "not briefed"}
            </td>
            <td className="px-2 text-right font-medium text-fg">
              {row.live ?? "not reported"}
            </td>
            <td className="px-2 text-right text-fg-secondary">
              {signed(row.delta)}
            </td>
            <td className="px-2 text-left text-fg-muted">{row.unit}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function Finding({ alert }: { readonly alert: ReplanAlert }): JSX.Element {
  const severity = SEVERITY[alert.severity];
  return (
    <li className="grid grid-cols-[auto_auto_1fr] items-baseline gap-x-3 border-b border-line-subtle px-3 py-2">
      <span
        className={`text-xs font-semibold uppercase tracking-label ${TONE_TEXT[severity.tone]}`}
      >
        {severity.label}
      </span>
      <span className="font-mono text-sm text-fg">{alert.code}</span>
      <span className="text-md text-fg">{ALERT_CODES[alert.code].label}</span>
      <span className="col-start-3 text-sm text-fg-secondary">
        {alert.message}
      </span>
    </li>
  );
}

/** What a replan found, with the briefed figure kept beside each live one. */
export function ReplanPanel({
  plan,
  sent,
  replan,
}: {
  readonly plan: PlanResult;
  readonly sent: TelemetrySnapshotRequest;
  readonly replan: ReplanResult;
}): JSX.Element {
  const verdict = replanVerdict(plan, replan);
  return (
    <section
      aria-label="Replan against live telemetry"
      className="border-b border-line"
    >
      <div
        className={`flex h-strip items-center justify-between border-b border-l-4 border-b-line px-3 ${TONE_CLASS[verdict.tone]}`}
      >
        <div>
          <p className="text-sm text-fg-secondary">
            Replan &middot; mode{" "}
            <span className="font-mono">{verdict.mode}</span>
          </p>
          <p className="text-xl font-semibold">{verdict.action}</p>
        </div>
        <p className="text-sm text-fg-secondary">
          Snapshot {replan.snapshot_age_s} s old &middot; thread{" "}
          <span className="font-mono text-fg">{replan.thread_id}</span>
        </p>
      </div>
      <Comparison rows={residualRows(plan, sent, replan)} />
      <div className="section-label flex h-header items-center bg-raised px-3">
        Findings
      </div>
      {replan.alerts.length === 0 ? (
        <p className="px-3 py-2 text-sm text-fg-muted">No alerts raised.</p>
      ) : (
        <ul>
          {replan.alerts.map((alert) => (
            <Finding key={alert.code} alert={alert} />
          ))}
        </ul>
      )}
    </section>
  );
}

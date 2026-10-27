"use client";

// Operator: a sUAS mission planner or safety officer preflighting one mission
// on a 14-inch 1080p laptop in a field vehicle or ops trailer, reading about
// 25 computed figures and a sealed assessment, deciding go or no-go and signing
// within two minutes. Tier 2 (analyst) density, dark theme. See
// docs/ui-standard.md.

import { useState } from "react";
import type { JSX } from "react";

import { advisoryNotice } from "@/lib/advisory";
import { acknowledgePlan, planMission } from "@/lib/api";
import type { AckAction, MissionRequest, PlanResult } from "@/lib/types";
import { useCatalog } from "@/lib/useCatalog";

import { AdvisoryBanner } from "./components/AdvisoryBanner";
import { MissionForm } from "./components/MissionForm";
import { ResultsPanel } from "./components/ResultsPanel";
import { ReviewPanel } from "./components/ReviewPanel";
import { UtcClock } from "./components/UtcClock";

function TopBar(): JSX.Element {
  return (
    <header className="flex h-topbar shrink-0 items-center justify-between border-b border-line bg-panel px-3">
      <div className="flex items-baseline gap-3">
        <h1 className="text-lg font-semibold text-fg">sUAS Mission Planner</h1>
        <span className="text-sm text-fg-muted">
          Deterministic calculator, operator-signed
        </span>
      </div>
      <UtcClock />
    </header>
  );
}

export default function MissionPlanner(): JSX.Element {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<PlanResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [threadId, setThreadId] = useState<string | null>(null);
  const [inputsEdited, setInputsEdited] = useState(false);
  const catalog = useCatalog();

  async function analyze(request: MissionRequest): Promise<void> {
    setLoading(true);
    setError(null);
    setResult(null);
    setInputsEdited(false);
    const outcome = await planMission({ ...request, thread_id: threadId });
    if (!outcome.ok) {
      setError(
        `Unable to reach the mission orchestration core: ${outcome.error}`,
      );
      setLoading(false);
      return;
    }
    setResult(outcome.data);
    setThreadId(outcome.data.thread_id);
    setLoading(false);
  }

  async function decide(action: AckAction): Promise<void> {
    const assessment = result?.assessment;
    if (result === null || !assessment) {
      return;
    }
    setLoading(true);
    setError(null);
    const outcome = await acknowledgePlan(result.thread_id, {
      action,
      actor: "dashboard-operator",
      inputs_hash: assessment.inputs_hash,
    });
    if (!outcome.ok) {
      setError(`Unable to record the acknowledgement: ${outcome.error}`);
      setLoading(false);
      return;
    }
    setResult(outcome.data);
    setLoading(false);
  }

  return (
    <div className="flex h-screen min-w-shell flex-col overflow-hidden bg-app text-fg">
      <TopBar />
      {/* No replan view yet (#94); it will pass its latest result here. */}
      <AdvisoryBanner notice={advisoryNotice(result, null)} />
      <div className="flex min-h-0 flex-1">
        <MissionForm
          loading={loading}
          aircraft={catalog.aircraft}
          payloads={catalog.payloads}
          catalogLoading={catalog.loading}
          catalogError={catalog.error}
          onEdit={() => {
            setInputsEdited(true);
          }}
          onAnalyze={(request) => {
            void analyze(request);
          }}
        />
        <main className="flex min-w-0 flex-1 flex-col border-r border-line bg-app">
          <div className="panel-header">
            <h2 className="section-label">Assessment</h2>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            <ResultsPanel loading={loading} error={error} result={result} />
          </div>
        </main>
        <ReviewPanel
          result={result}
          busy={loading}
          inputsEdited={inputsEdited}
          onDecide={(action) => {
            void decide(action);
          }}
        />
      </div>
    </div>
  );
}

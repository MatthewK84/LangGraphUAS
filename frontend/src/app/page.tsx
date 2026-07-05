"use client";

import { useState } from "react";
import type { JSX } from "react";

import { planMission } from "@/lib/api";
import type { MissionRequest, PlanResult } from "@/lib/types";

import { MissionForm } from "./components/MissionForm";
import { ResultsPanel } from "./components/ResultsPanel";

export default function MissionPlanner(): JSX.Element {
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<PlanResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [threadId, setThreadId] = useState<string | null>(null);

  async function analyze(request: MissionRequest): Promise<void> {
    setLoading(true);
    setError(null);
    setResult(null);
    const outcome = await planMission({ ...request, thread_id: threadId });
    if (!outcome.ok) {
      setError(`Unable to reach the mission orchestration core: ${outcome.error}`);
      setLoading(false);
      return;
    }
    setResult(outcome.data);
    setThreadId(outcome.data.thread_id);
    setLoading(false);
  }

  return (
    <main className="min-h-screen bg-slate-900 text-slate-100 p-8 font-sans">
      <div className="max-w-6xl mx-auto space-y-8">
        <div>
          <h1 className="text-3xl font-bold tracking-tight text-white">
            sUAS Intelligent Mission Planner
          </h1>
          <p className="text-slate-400 mt-1">
            Deterministic physics engines coupled with LangGraph orchestration.
          </p>
        </div>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
          <MissionForm
            loading={loading}
            onAnalyze={(request) => {
              void analyze(request);
            }}
          />
          <div className="lg:col-span-2">
            <ResultsPanel loading={loading} error={error} result={result} />
          </div>
        </div>
      </div>
    </main>
  );
}

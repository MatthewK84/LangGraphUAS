// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { planFailure } from "@/lib/failure";
import { ADVISORY_PLAN, BRIEFED_PLAN } from "@/test/fixtures";

import { ResultsPanel } from "./ResultsPanel";

afterEach(cleanup);

describe("results panel states (#95)", () => {
  it("writes the deterministic brief as the calculator's, not a model's", () => {
    render(<ResultsPanel loading={false} error={null} result={BRIEFED_PLAN} />);
    screen.getByRole("heading", { name: "Safety officer brief" });
    screen.getByText("Deterministic: no language model wrote this brief.");
    expect(screen.queryByText(/language model from the sealed/)).toBeNull();
  });

  it("notes that a model-written brief is fully grounded", () => {
    const written = {
      ...BRIEFED_PLAN,
      report: "Winds are light; proceed.",
      report_source: "model" as const,
      narrative_source: "model" as const,
    };
    render(<ResultsPanel loading={false} error={null} result={written} />);
    screen.getByText("Model narrative: every number matches the sealed result.");
    expect(screen.queryByText(/Model narrative withheld/)).toBeNull();
  });

  it("lists one withheld figure beside the deterministic brief", () => {
    const withheld = {
      ...BRIEFED_PLAN,
      report: "Mission status: NO-GO (advisory).",
      report_source: "deterministic" as const,
      narrative_source: "deterministic" as const,
      ungrounded_numerics: [{ value: "225.7", unit: "Wh" }],
      narrative_reason: "not found in the sealed result",
    };
    render(<ResultsPanel loading={false} error={null} result={withheld} />);
    screen.getByText(
      "Model narrative withheld: 225.7 Wh not found in the sealed result. Showing deterministic brief.",
    );
  });

  it("lists each withheld figure when several fail the seal", () => {
    const withheld = {
      ...BRIEFED_PLAN,
      report: "Mission status: GO (advisory).",
      report_source: "deterministic" as const,
      narrative_source: "deterministic" as const,
      ungrounded_numerics: [
        { value: "3", unit: "m/s" },
        { value: "45", unit: "%" },
      ],
      narrative_reason: "not found in the sealed result",
    };
    render(<ResultsPanel loading={false} error={null} result={withheld} />);
    screen.getByText(
      "Model narrative withheld: 3 m/s, 45 % not found in the sealed result. Showing deterministic brief.",
    );
  });

  it("labels the brief from report_source, not its wording", () => {
    // A failed model call's fallback lacks the no-key sentence; the backend
    // still knows no model wrote it.
    const fallback = {
      ...BRIEFED_PLAN,
      report: "Mission status: GO. Narrative unavailable.",
      report_source: "deterministic" as const,
    };
    render(<ResultsPanel loading={false} error={null} result={fallback} />);
    screen.getByText("Deterministic: no language model wrote this brief.");
    expect(screen.queryByText(/language model from the sealed/)).toBeNull();
  });

  it("fakes no model at work while computing", () => {
    const { container } = render(
      <ResultsPanel loading error={null} result={null} />,
    );
    expect(container.textContent).not.toMatch(/\bAI\b|copilot|prompting/i);
    screen.getByText("Computing the assessment.");
  });

  it("says the backend is down, readably, and keeps the raw reason", () => {
    const failure = planFailure("plan", "Backend returned status 502");
    render(<ResultsPanel loading={false} error={failure} result={null} />);
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain("Planner backend not answering");
    expect(alert.textContent).toContain("Nothing was computed or recorded.");
    expect(alert.textContent).toContain("Backend returned status 502");
  });

  it("says so when a plan comes back with no figures at all", () => {
    const empty = { ...ADVISORY_PLAN, calculations: null, weather: null };
    render(<ResultsPanel loading={false} error={null} result={empty} />);
    screen.getByText("The planner returned no figures for this mission.");
  });

  it("explains the empty panel before any plan", () => {
    render(<ResultsPanel loading={false} error={null} result={null} />);
    screen.getByText(/^No plan yet\./);
  });
});

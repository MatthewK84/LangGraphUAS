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

  it("marks a model-written brief as one to check against the figures", () => {
    const written = { ...BRIEFED_PLAN, report: "Winds are light; proceed." };
    render(<ResultsPanel loading={false} error={null} result={written} />);
    screen.getByText(
      "Written by a language model from the sealed figures. Check it against them.",
    );
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

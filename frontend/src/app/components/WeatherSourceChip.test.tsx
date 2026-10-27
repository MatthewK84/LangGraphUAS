// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import type { WeatherSource } from "@/lib/types";
import { ADVISORY_PLAN } from "@/test/fixtures";

import { ResultsPanel } from "./ResultsPanel";
import { WeatherSourceChip } from "./WeatherSourceChip";

afterEach(cleanup);

const LABELS: Readonly<Record<WeatherSource, string>> = {
  live: "Live",
  cached_fresh: "Cached, fresh",
  cached_stale: "Cached, stale",
  fallback: "Fallback",
  error: "Provider error",
  fixture: "Demo fixture",
};

describe("weather source chip (#93)", () => {
  it.each(Object.entries(LABELS))("renders %s as %s", (source, label) => {
    render(<WeatherSourceChip source={source as WeatherSource} />);
    expect(screen.getByText(label)).toBeDefined();
  });

  it("shows the chip in the weather table for the plan's own source", () => {
    const plan = {
      ...ADVISORY_PLAN,
      weather: ADVISORY_PLAN.weather && {
        ...ADVISORY_PLAN.weather,
        source: "cached_fresh" as const,
      },
    };
    render(<ResultsPanel loading={false} error={null} result={plan} />);
    const row = screen.getByRole("row", { name: /Source/ });
    expect(row.textContent).toContain("Cached, fresh");
    expect(row.textContent).not.toContain("Fallback");
  });
});

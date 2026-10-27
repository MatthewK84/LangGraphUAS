// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ADVISORY_PLAN, BRIEFED_PLAN } from "@/test/fixtures";
import { stubBackend } from "@/test/planner";

import MissionPlanner from "./page";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  Reflect.deleteProperty(navigator, "geolocation");
});

function stubPosition(latitude: number, longitude: number): void {
  const geolocation = {
    getCurrentPosition: (ok: PositionCallback) => {
      ok({ coords: { latitude, longitude } } as GeolocationPosition);
    },
  };
  Object.defineProperty(navigator, "geolocation", {
    value: geolocation,
    configurable: true,
  });
}

function valueOf(label: string): string {
  return screen.getByLabelText<HTMLInputElement>(label).value;
}

describe("use my current location", () => {
  it("fills latitude and longitude to five decimal places (about 1 m)", async () => {
    stubBackend(ADVISORY_PLAN, BRIEFED_PLAN);
    stubPosition(38.871144321, -77.056087654);
    const user = userEvent.setup();
    render(<MissionPlanner />);

    await user.click(
      await screen.findByRole("button", { name: "Use my current location" }),
    );

    await waitFor(() => {
      expect(valueOf("Latitude")).toBe("38.87114");
    });
    expect(valueOf("Longitude")).toBe("-77.05609");
  });
});

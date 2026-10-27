// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { OPERATIONAL_PLAN, REPLAN } from "@/test/fixtures";
import { analyzeMission, replanMission, stubBackend } from "@/test/planner";

import MissionPlanner from "./page";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const BANNER = { name: "Advisory: not a clearance" };
const SIGNED = { ...OPERATIONAL_PLAN, awaiting_ack: false, report: "Brief." };

describe("replan on the planner page (#94)", () => {
  it("turns an operational plan advisory on a single watch alert", async () => {
    stubBackend(OPERATIONAL_PLAN, SIGNED, REPLAN);
    const user = userEvent.setup();
    render(<MissionPlanner />);
    await analyzeMission(user);
    const card = await screen.findByRole("region", {
      name: "Assessment review",
    });
    await user.click(
      within(card).getByRole("button", {
        name: "Acknowledge and generate brief",
      }),
    );
    await screen.findByRole("heading", { name: "AI Safety Officer Report" });
    expect(screen.queryByRole("region", BANNER)).toBeNull();

    await replanMission(user);

    await screen.findByRole("region", {
      name: "Replan against live telemetry",
    });
    expect(screen.getByRole("region", BANNER)).toBeDefined();
  });

  it("offers no replan before the plan is signed", async () => {
    stubBackend(OPERATIONAL_PLAN);
    render(<MissionPlanner />);
    await analyzeMission(userEvent.setup());
    await screen.findByRole("region", { name: "Assessment review" });
    expect(screen.queryByRole("form", { name: "Live telemetry" })).toBeNull();
  });
});

// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ADVISORY_PLAN, BRIEFED_PLAN } from "@/test/fixtures";
import { analyzeMission, stubBackend } from "@/test/planner";

import MissionPlanner from "./page";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

const BRIEF = { name: "Safety officer brief" };
const CONFIRM = { name: "Acknowledge and generate brief" };

async function reviewCard(): Promise<HTMLElement> {
  return screen.findByRole("region", { name: "Assessment review" });
}

describe("compute, review, then ack (#92)", () => {
  it("renders no brief before the signature, even if one was sent", async () => {
    stubBackend({ ...ADVISORY_PLAN, report: BRIEFED_PLAN.report });
    render(<MissionPlanner />);
    await analyzeMission(userEvent.setup());
    await reviewCard();
    expect(screen.queryByRole("heading", BRIEF)).toBeNull();
    expect(screen.queryByText(BRIEFED_PLAN.report)).toBeNull();
  });

  it("renders the brief once the assessment is signed", async () => {
    stubBackend(ADVISORY_PLAN, BRIEFED_PLAN);
    const user = userEvent.setup();
    render(<MissionPlanner />);
    await analyzeMission(user);
    const card = await reviewCard();
    await user.click(within(card).getByRole("checkbox"));
    await user.click(within(card).getByRole("button", CONFIRM));
    expect(await screen.findByRole("heading", BRIEF)).toBeDefined();
    expect(screen.getByText(BRIEFED_PLAN.report)).toBeDefined();
    expect(screen.getByText(/Assessment signed/)).toBeDefined();
  });

  it("disables a pending confirm when any input is edited", async () => {
    stubBackend(ADVISORY_PLAN);
    const user = userEvent.setup();
    render(<MissionPlanner />);
    await analyzeMission(user);
    const card = await reviewCard();
    await user.click(within(card).getByRole("checkbox"));
    const confirm = within(card).getByRole("button", CONFIRM);
    expect(confirm).toHaveProperty("disabled", false);

    await user.type(screen.getByLabelText(/Distance/), "0");

    expect(confirm).toHaveProperty("disabled", true);
    expect(within(card).getByText(/Inputs edited since this assessment/));
  });

  it("shows the full inputs hash it will sign", async () => {
    stubBackend(ADVISORY_PLAN);
    render(<MissionPlanner />);
    await analyzeMission(userEvent.setup());
    const card = await reviewCard();
    const hash = ADVISORY_PLAN.assessment?.inputs_hash ?? "";
    expect(within(card).getByText(hash)).toBeDefined();
  });
});

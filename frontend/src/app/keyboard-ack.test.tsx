// @vitest-environment jsdom
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { UserEvent } from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ADVISORY_PLAN, BRIEFED_PLAN } from "@/test/fixtures";
import { stubBackend } from "@/test/planner";

import MissionPlanner from "./page";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

/** Press Tab until `target` has focus; fail if it is not in the tab order. */
async function tabTo(user: UserEvent, target: HTMLElement): Promise<void> {
  for (let presses = 0; presses < 60; presses += 1) {
    if (document.activeElement === target) {
      return;
    }
    await user.tab();
  }
  throw new Error(`not reachable by Tab: ${target.outerHTML.slice(0, 80)}`);
}

/** Fill the location and analyze with the keyboard alone. */
async function analyzeByKeyboard(user: UserEvent): Promise<HTMLElement> {
  await screen.findByRole("option", { name: "DJI Matrice 350 RTK" });
  await tabTo(user, screen.getByLabelText(/Latitude/));
  await user.keyboard("38.87114");
  await tabTo(user, screen.getByLabelText(/Longitude/));
  await user.keyboard("-77.05581");
  await tabTo(
    user,
    screen.getByRole("button", { name: "Analyze flight feasibility" }),
  );
  await user.keyboard("{Enter}");
  return screen.findByRole("region", { name: "Assessment review" });
}

describe("the acknowledgement without a mouse (#98)", () => {
  it("signs by keyboard and lands focus on the outcome", async () => {
    stubBackend(ADVISORY_PLAN, BRIEFED_PLAN);
    const user = userEvent.setup();
    render(<MissionPlanner />);
    const card = await analyzeByKeyboard(user);

    await tabTo(user, within(card).getByRole("checkbox"));
    await user.keyboard(" ");
    await tabTo(
      user,
      within(card).getByRole("button", {
        name: "Acknowledge and generate brief",
      }),
    );
    await user.keyboard("{Enter}");

    expect(
      await screen.findByRole("heading", { name: "Safety officer brief" }),
    ).toBeDefined();
    // The card that held focus is gone; focus must not fall to the body.
    expect(document.activeElement).toBe(screen.getByText(/Assessment signed/));
  });

  it("aborts by keyboard and lands focus on the outcome", async () => {
    stubBackend(ADVISORY_PLAN, {
      ...ADVISORY_PLAN,
      awaiting_ack: false,
      aborted: true,
    });
    const user = userEvent.setup();
    render(<MissionPlanner />);
    const card = await analyzeByKeyboard(user);

    await tabTo(user, within(card).getByRole("button", { name: "Abort" }));
    await user.keyboard("{Enter}");

    expect(await screen.findByText(/Assessment aborted/)).toBeDefined();
    expect(document.activeElement).toBe(screen.getByText(/Assessment aborted/));
  });
});

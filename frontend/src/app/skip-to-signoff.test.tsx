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

const SKIP = { name: "Skip to sign-off" };
const CONFIRM = { name: "Acknowledge and generate brief" };

describe("skip to the sign-off", () => {
  it("is the next stop after Analyze, before any figure", async () => {
    stubBackend(ADVISORY_PLAN, BRIEFED_PLAN);
    const user = userEvent.setup();
    render(<MissionPlanner />);
    await analyzeMission(user);
    await screen.findByRole("region", { name: "Assessment review" });

    await user.tab();

    expect(document.activeElement).toBe(screen.getByRole("link", SKIP));
  });

  it("reaches Acknowledge in two presses instead of past every figure", async () => {
    stubBackend(ADVISORY_PLAN, BRIEFED_PLAN);
    const user = userEvent.setup();
    render(<MissionPlanner />);
    await analyzeMission(user);
    const card = await screen.findByRole("region", {
      name: "Assessment review",
    });

    await user.tab();
    expect(document.activeElement).toBe(screen.getByRole("link", SKIP));
    await user.keyboard("{Enter}");
    await user.tab();
    expect(document.activeElement).toBe(within(card).getByRole("checkbox"));
    await user.keyboard(" ");
    await user.tab();
    expect(document.activeElement).toBe(
      within(card).getByRole("button", CONFIRM),
    );
    await user.keyboard("{Enter}");

    expect(
      await screen.findByRole("heading", { name: "Safety officer brief" }),
    ).toBeDefined();
  });

  it("is not offered before there is anything to sign", async () => {
    stubBackend(ADVISORY_PLAN);
    render(<MissionPlanner />);
    await screen.findByRole("option", { name: "DJI Matrice 350 RTK" });
    expect(screen.queryByRole("link", SKIP)).toBeNull();
  });
});

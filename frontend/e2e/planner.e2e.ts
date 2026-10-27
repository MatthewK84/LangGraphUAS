// The dashboard and the planner, in separate containers, agree (#116).
//
// Runs against Compose in demo mode (scripts/e2e.sh): the backend uses its
// fixture weather reading, so no live METAR is needed and every plan is
// advisory. scripts/compose_smoke.py, which e2e.sh runs first, holds the
// catalog to src/lib/types.ts field by field; this suite drives what an
// operator does in a real browser: the catalog renders, a plan, an ack.
import { expect, test } from "@playwright/test";

test("catalog load, plan and ack run through both containers", async ({
  page,
}) => {
  await page.goto("/");

  const aircraft = page.getByLabel("Aircraft Platform");
  await expect(
    aircraft.locator("option", { hasText: "Skydio X10D" }),
  ).toHaveCount(1);
  await expect(
    page.getByText("Unable to load the platform catalog"),
  ).toHaveCount(0);
  // A renamed catalog field renders as a blank or "undefined" option.
  for (const label of await aircraft.locator("option").allTextContents()) {
    expect(label.trim()).not.toBe("");
    expect(label).not.toContain("undefined");
  }
  await aircraft.selectOption("Skydio_X10D");
  // Location is required; the demo backend serves fixture weather for it.
  await page.getByLabel("Latitude").fill("34.0");
  await page.getByLabel("Longitude").fill("-80.0");

  const planned = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/plan") &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Analyze flight feasibility" })
    .click();
  const plan = (await (await planned).json()) as {
    weather: { source: string } | null;
  };
  // Demo mode's fixture reading: no live provider was asked.
  expect(plan.weather?.source).toBe("fixture");

  const review = page.getByRole("region", { name: "Assessment review" });
  await expect(review).toBeVisible();
  await expect(review).toContainText("advisory");
  // Compute, review, then ack (#92): the brief does not exist before the
  // signature, and an edit after the assessment withdraws the confirm.
  const brief = page.getByRole("heading", { name: "Safety officer brief" });
  await expect(brief).toHaveCount(0);
  const confirm = review.getByRole("button", {
    name: "Acknowledge and generate brief",
  });
  await review.getByRole("checkbox").check();
  await expect(confirm).toBeEnabled();
  await page.getByLabel("Distance").fill("5001");
  await expect(confirm).toBeDisabled();
  await page
    .getByRole("button", { name: "Analyze flight feasibility" })
    .click();
  await expect(review).toBeVisible();
  await expect(brief).toHaveCount(0);

  await review.getByRole("checkbox").check();
  await confirm.click();

  await expect(review).toHaveCount(0);
  await expect(brief).toHaveCount(1);
  await expect(brief.locator("xpath=..")).not.toContainText(
    "Unable to record the acknowledgement",
  );
  await expect(brief.locator("xpath=following-sibling::div")).not.toBeEmpty();

  // Provenance drawer (#96): a figure's basis opens the record of every
  // field it rests on, and Escape hands focus back to the figure.
  const basis = page.getByRole("button", {
    name: /show the provenance of Hover power/,
  });
  await basis.click();
  const drawer = page.getByRole("region", { name: /^Provenance: Hover power/ });
  await expect(drawer).toBeVisible();
  await expect(drawer.getByRole("row").nth(1)).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(drawer).toHaveCount(0);
  await expect(basis).toBeFocused();

  // Replan against telemetry after the signature (#94): the briefed figure
  // stays beside the live one, and the advisory strip names the alerts.
  const telemetry = page.getByRole("form", { name: "Live telemetry" });
  await telemetry.getByLabel("State of charge").fill("42");
  await telemetry.getByLabel("Remaining leg").fill("1800");
  await telemetry.getByLabel("Outside air").fill("4");
  await telemetry
    .getByRole("button", { name: "Replan against telemetry" })
    .click();
  const replan = page.getByRole("region", {
    name: "Replan against live telemetry",
  });
  await expect(replan).toBeVisible();
  await expect(
    replan.getByRole("row", { name: /Margin after mission/ }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Advisory: not a clearance" }),
  ).toBeVisible();
});
